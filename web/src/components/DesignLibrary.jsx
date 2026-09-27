import { useMemo } from "react";
import { Download } from "lucide-react";
import { GROUNDS, MASCOTS, groundUses, templateOf } from "../lib/cards/library";
import { mascotDuty } from "../lib/cards/studio";
import { useLang } from "../lib/i18n";

/* Studio's Designs library: Wan's own photographs (the grounds behind the cards) and the mascot poses, each saying what
   uses it by default. "Who uses it" is derived from the same rules a render follows (rules/cards.json for grounds,
   pickMascotFor for poses), never restated, so this page and the artwork cannot disagree. */
export default function DesignLibrary() {
  const { t, lang } = useLang();
  const duty = useMemo(() => mascotDuty(MASCOTS), []);
  const tplName = (k) => { const x = templateOf(k); return x ? (lang === "bm" ? x.name : x.en) : k; };
  const rail = "flex gap-3 overflow-x-auto pb-2";
  return (
    <section className="mt-12" aria-labelledby="lib-h">
      <h2 id="lib-h" className="text-xl">{t("Perpustakaan reka bentuk", "Design library")}</h2>
      <p className="mt-1 text-[12px] text-muted">{t("Gambar anda sendiri (dari OneDrive, melalui Studio) di belakang kad, dan pose maskot. Pilih di mana-mana editor slaid sebagai latar atau maskot.",
        "Your own photographs (from OneDrive, through Studio) behind the cards, and the mascot poses. Pick them in any slide editor as a background or a mascot.")}</p>

      <h3 className="mt-4 text-sm font-medium">{t("Latar: {n} gambar", "Grounds: {n} photographs", { n: GROUNDS.length })}</h3>
      <div className={rail} style={{ scrollSnapType: "x mandatory" }}>
        {GROUNDS.map((g) => {
          const u = groundUses(g.k);
          const uses = [...u.domains, ...u.angles.map((a) => `LinkedIn ${a}`), ...(u.linkedinDefault ? [t("LinkedIn (lalai)", "LinkedIn (default)")] : [])];
          return (
            <figure key={g.k} className="w-40 shrink-0 overflow-hidden rounded-tile border border-line bg-surface" style={{ scrollSnapAlign: "start" }}>
              <img src={g.url} alt={g.alt} loading="lazy" className="aspect-[4/5] w-full object-cover" />
              <figcaption className="space-y-0.5 p-2 text-[11px]">
                <span className="flex items-center justify-between gap-1 font-medium">{g.name}
                  <a href={g.url} download className="text-muted hover:text-ink" aria-label={t("Muat turun {n}", "Download {n}", { n: g.name })}><Download size={11} /></a></span>
                <span className="block text-muted">{uses.length ? `${t("Lalai untuk", "Default for")}: ${uses.join(", ")}` : t("Pilih sendiri", "Pick it yourself")}</span>
              </figcaption>
            </figure>
          );
        })}
      </div>

      <h3 className="mt-4 text-sm font-medium">{t("Pose maskot: {n}", "Mascot poses: {n}", { n: MASCOTS.length })}</h3>
      <div className={rail} style={{ scrollSnapType: "x mandatory" }}>
        {MASCOTS.map((m) => (
          <figure key={m.k} className="w-36 shrink-0 overflow-hidden rounded-tile border border-line bg-surface-2/50" style={{ scrollSnapAlign: "start" }}>
            <img src={m.url} alt={lang === "bm" ? m.name : m.en} loading="lazy" className="aspect-square w-full object-contain p-2" />
            <figcaption className="space-y-0.5 p-2 text-[11px]">
              <span className="block font-medium">{lang === "bm" ? m.name : m.en}</span>
              <span className="block text-muted">{(duty[m.k] || []).length
                ? `${t("Dipilih oleh", "Picked by")}: ${duty[m.k].map(tplName).join(", ")}` : t("Pilih sendiri", "Pick it yourself")}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

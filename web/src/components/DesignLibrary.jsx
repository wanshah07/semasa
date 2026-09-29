import { useMemo } from "react";
import { NotchedProjectCard } from "@/components/ui/notched-project-card";
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
      {/* each photograph as a notched card (components/ui/notched-project-card.tsx, Wan 29 Sep 2026: "add this for
          card"); the card opens the full photograph in a new tab, where it can be saved */}
      <div className="mt-3 grid gap-x-5 gap-y-10 sm:grid-cols-2 xl:grid-cols-3">
        {GROUNDS.map((g) => {
          const u = groundUses(g.k);
          const uses = [...u.domains, ...u.angles.map((a) => `LinkedIn ${a}`), ...(u.linkedinDefault ? [t("LinkedIn (lalai)", "LinkedIn (default)")] : [])];
          return (
            <NotchedProjectCard key={g.k} href={g.url} target="_blank" rel="noreferrer" imgLoading="lazy"
              aria-label={t("Buka {n} dalam tab baharu", "Open {n} in a new tab", { n: g.name })}
              title={g.name} image={g.url} imageAlt={g.alt} badge={uses.length ? t("Lalai", "Default") : undefined}
              description={uses.length ? `${t("Lalai untuk", "Default for")}: ${uses.join(", ")}` : t("Pilih sendiri", "Pick it yourself")}
              tags={uses.slice(0, 4)} />
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

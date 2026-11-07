import { useMemo } from "react";
import TileGrid from "./TileGrid";
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
  const usesOf = (g) => { const u = groundUses(g.k); return [...u.domains, ...u.angles.map((a) => `LinkedIn ${a}`), ...(u.linkedinDefault ? [t("LinkedIn (lalai)", "LinkedIn (default)")] : [])]; };
  const groundLine = (g) => { const u = usesOf(g); return u.length ? `${t("Lalai", "Default")}: ${u.slice(0, 3).join(", ")}` : t("Pilih sendiri", "Pick it yourself"); };
  return (
    <section className="mt-12" aria-labelledby="lib-h">
      <h2 id="lib-h" className="text-xl">{t("Perpustakaan reka bentuk", "Design library")}</h2>
      <p className="mt-1 text-[12px] text-muted">{t("Gambar anda sendiri (dari OneDrive, melalui Studio) di belakang kad, dan pose maskot. Pilih di mana-mana editor slaid sebagai latar atau maskot.",
        "Your own photographs (from OneDrive, through Studio) behind the cards, and the mascot poses. Pick them in any slide editor as a background or a mascot.")}</p>

      {/* compact tiles, 8 to a row like every Create library (Wan, 7 Nov 2026: "for poster make sure follow like video, 8 card
          per row"); a tile opens the photograph or pose with what uses it, and the photograph opens full size in a new tab */}
      <h3 className="mt-4 mb-3 text-sm font-medium">{t("Latar: {n} gambar", "Grounds: {n} photographs", { n: GROUNDS.length })}</h3>
      <TileGrid items={GROUNDS.map((g) => ({ id: `g:${g.k}`, kind: "image", src: g.url, label: g.name, sub: groundLine(g) }))}
        detail={(it) => {
          const g = GROUNDS.find((x) => `g:${x.k}` === it.id);
          if (!g) return null;
          const uses = usesOf(g);
          return (
            <div className="space-y-3" data-ground-detail>
              <img src={g.url} alt={g.alt} className="max-h-[60vh] w-full rounded-tile object-contain" />
              <p className="text-sm">{uses.length ? `${t("Lalai untuk", "Default for")}: ${uses.join(", ")}` : t("Pilih sendiri", "Pick it yourself")}</p>
              <a href={g.url} target="_blank" rel="noreferrer" className="text-sm text-accent underline">{t("Buka saiz penuh dalam tab baharu", "Open full size in a new tab")}</a>
            </div>
          );
        }}
        empty={t("Tiada gambar.", "No photographs.")} />

      <h3 className="mt-8 mb-3 text-sm font-medium">{t("Pose maskot: {n}", "Mascot poses: {n}", { n: MASCOTS.length })}</h3>
      <TileGrid items={MASCOTS.map((m) => ({ id: `m:${m.k}`, kind: "image", src: m.url, label: lang === "bm" ? m.name : m.en,
        sub: (duty[m.k] || []).length ? `${t("Dipilih oleh", "Picked by")}: ${duty[m.k].map(tplName).join(", ")}` : t("Pilih sendiri", "Pick it yourself") }))}
        detail={(it) => {
          const m = MASCOTS.find((x) => `m:${x.k}` === it.id);
          if (!m) return null;
          return (
            <div className="space-y-3" data-mascot-detail>
              <img src={m.url} alt={lang === "bm" ? m.name : m.en} className="mx-auto max-h-[50vh] object-contain" />
              <p className="text-sm">{(duty[m.k] || []).length ? `${t("Dipilih oleh", "Picked by")}: ${duty[m.k].map(tplName).join(", ")}` : t("Pilih sendiri", "Pick it yourself")}</p>
            </div>
          );
        }}
        empty={t("Tiada pose.", "No poses.")} />
    </section>
  );
}

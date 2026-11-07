import { useState } from "react";
import { Loader2, TrendingUp } from "lucide-react";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { BUILTIN } from "../lib/hookStyles";
import { SWITCH_KEY, learningOf, learningOn, learningRows, ratePct } from "../lib/hookLearning";
import Card from "./ui/Card";

/* Which hook shapes earn views and interaction (Wan, 7 Nov 2026: "will update the instructions automatically based on top viewers
   and interaction post"). The daily Hook learning run ranks the shapes on real results and the writers are pointed at the best three as
   a hint, never a rule (backend/semasa/hook_learning.py). This card shows the numbers behind it and keeps the one switch. */

export default function HookLearning({ settings, save, onToast }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const learn = learningOf(settings?.hook_learning);
  const on = learningOn(settings?.[SWITCH_KEY]);
  const rows = learningRows(learn.ranking);

  async function flip() {
    setBusy(true);
    try {
      await save(SWITCH_KEY, { enabled: !on });
      onToast?.(on ? t("Pembelajaran hook dimatikan.", "Hook learning switched off.") : t("Pembelajaran hook dihidupkan.", "Hook learning switched on."), "ok");
    } catch (e) {
      onToast?.(e.message, "danger");
    } finally { setBusy(false); }
  }

  return (
    <Card className="space-y-3 p-4" data-hook-learning>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-lg"><TrendingUp size={16} className="text-accent" /> {t("Hook yang berjaya", "Hooks that work")}</h3>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={on} disabled={busy} onChange={flip} data-hook-learning-switch /> {t("Belajar daripada prestasi", "Learn from results")}
          {busy && <Loader2 size={13} className="animate-spin" />}
        </label>
      </div>
      <p className="max-w-3xl text-[12px] text-muted">
        {t(`Setiap hari, selepas angka Buffer dikemas kini, Semasa mengukur pos dan filem ${learn.windowDays} hari lalu: tontonan dan kadar interaksi (reaksi, komen, kongsi, simpan, klik), dikaitkan dengan bentuk hook yang digunakan. Tiga bentuk teratas ditunjukkan kepada penulis sebagai petunjuk, bukan peraturan: mereka masih boleh pilih bentuk lain jika ia lebih sesuai. Bentuk perlu sekurang-kurangnya ${learn.minPosts} keputusan sebelum disenaraikan. LinkedIn tiada angka, jadi tidak dikira.`,
          `Every day, after Buffer's figures refresh, Semasa measures the last ${learn.windowDays} days of posts and films: views and interaction rate (reactions, comments, shares, saves, clicks), joined to the hook shape each used. The top three shapes are shown to the writers as a hint, never a rule: they may still choose another shape when it fits better. A shape needs at least ${learn.minPosts} results before it is listed. LinkedIn has no figures, so it is not counted.`)}
      </p>
      {rows.length === 0 ? (
        <p className="rounded-tile bg-surface-2 p-3 text-xs text-muted" data-hook-learning-empty>
          {learn.at
            ? t(`Belum cukup keputusan: ${learn.measured} diukur, tiada bentuk lagi dengan ${learn.minPosts} keputusan atau lebih.`,
              `Not enough results yet: ${learn.measured} measured, no shape with ${learn.minPosts} or more results yet.`)
            : t("Belum dijalankan. Larian pertama berlaku selepas angka Buffer seterusnya (workflow Hook learning di GitHub).",
              "Not run yet. The first run follows Buffer's next figures (the Hook learning workflow on GitHub).")}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs" data-hook-learning-table>
            <thead className="text-muted"><tr>
              <th className="py-1 pr-3">#</th><th className="pr-3">{t("Bentuk", "Shape")}</th><th className="pr-3">{t("Sumber", "Source")}</th>
              <th className="pr-3">{t("Keputusan", "Results")}</th><th className="pr-3">{t("Purata tontonan", "Avg views")}</th>
              <th className="pr-3">{t("Interaksi", "Interaction")}</th><th>{t("Skor", "Score")}</th></tr></thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.style}-${r.shape}`} className={r.top && on ? "font-medium text-ink" : "text-muted"} data-hook-row={r.shape} data-top={r.top}>
                  <td className="py-1 pr-3">{i + 1}</td><td className="pr-3">{r.shape}{r.top && on ? " ★" : ""}</td>
                  <td className="pr-3">{!r.style || r.style === BUILTIN ? t("25 terbina", "built-in 25") : t("gaya saya", "my style")}</td>
                  <td className="pr-3">{r.n}{r.films ? ` (${r.films} ${t("filem", "films")})` : ""}</td>
                  <td className="pr-3">{Math.round(r.views).toLocaleString()}</td><td className="pr-3">{ratePct(r.rate)}</td><td>{r.score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {learn.at && <p className="text-[11px] text-muted" data-hook-learning-at>{t("Diukur", "Measured")} {timeAgo(learn.at)} · {learn.measured} {t("keputusan", "results")}{on ? "" : ` · ${t("dimatikan: penulis tidak diberi petunjuk", "off: the writers are given no hint")}`}</p>}
    </Card>
  );
}

import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Loader2, RadioTower, XCircle } from "lucide-react";
import { TABLES, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { EVERY_MIN, freshness, pulseOf, runPulse, tally } from "../lib/apiPulse";
import Button from "./ui/Button";

/* The API pulse: when the robots were last checked (every 5 minutes by the clock, supabase/075_api_pulse.sql → Edge Function
   semasa-pulse) and a "Semak sekarang" that runs the same check now with the signed-in user's login. The robot cards above redraw
   from the realtime status rows by themselves; this strip only says when and shows each robot's answer. No key passes through. */

const TONE = { live: "text-ok", late: "text-warn", stopped: "text-danger", none: "text-muted" };

export default function ApiPulse({ onToast }) {
  const { t } = useLang();
  // the settings table on realtime (075 publishes it), so a pulse written by the clock shows the second it lands
  const settingsT = useTable(TABLES.settings, { enabled: true, select: "key,value", order: "key", ascending: true, limit: 500, realtime: true, everyMs: 60_000 });
  const settings = useMemo(() => Object.fromEntries(settingsT.rows.map((r) => [r.key, r.value])), [settingsT.rows]);
  const pulse = useMemo(() => pulseOf(settings), [settings]);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(id); }, []);
  const fresh = freshness(pulse.at, now);
  const count = tally(pulse.results);

  const check = async () => {
    setBusy(true); setNote("");
    const { data: s } = await supabase.auth.getSession();
    const r = await runPulse({ url: import.meta.env.VITE_SUPABASE_URL, anon: import.meta.env.VITE_SUPABASE_ANON_KEY, token: s?.session?.access_token });
    setBusy(false);
    if (r.missing) setNote(t("Fungsi semasa-pulse belum dipasang: gabungkan ke main dan biar \"Deploy functions\" berjalan.", "The semasa-pulse function is not deployed yet: merge to main and let \"Deploy functions\" run."));
    else if (!r.ok) setNote(r.error);
    else {
      await settingsT.reload();
      onToast?.(t("Semakan selesai", "Check done"), "ok");
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-tile bg-surface-2/60 px-3 py-2 text-xs" data-api-pulse>
      <span className={`inline-flex items-center gap-1 ${TONE[fresh]}`}>
        <RadioTower size={13} />
        {fresh === "none"
          ? t("Belum ada denyut: jalankan supabase/075_api_pulse.sql dan cipta rahsia semasa_pulse_secret.", "No pulse yet: run supabase/075_api_pulse.sql and create the semasa_pulse_secret.")
          : <>{t("Dikemas kini", "Updated")} {timeAgo(pulse.at, now)}{fresh !== "live" && <> · {t("jam denyut terlepas tik", "the pulse clock has missed ticks")}</>}</>}
      </span>
      {pulse.at && (
        <span className="text-muted">
          {t(`setiap ${pulse.everyMin || EVERY_MIN} minit`, `every ${pulse.everyMin || EVERY_MIN} minutes`)} · {count.ok}/{count.asked} {t("menjawab", "answered")}
          {pulse.tookMs ? ` · ${(pulse.tookMs / 1000).toFixed(1)} s` : ""}
        </span>
      )}
      <span className="flex flex-wrap items-center gap-1">
        {pulse.results.map((r) => (
          <span key={r.slug} title={r.skipped || r.error || (r.ms != null ? `${r.ms} ms` : "")}
            className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 ${r.skipped ? "bg-surface-2 text-muted" : r.ok ? "bg-ok/15 text-ok" : "bg-danger/15 text-danger"}`}>
            {r.ok ? <CheckCircle2 size={11} /> : <XCircle size={11} />}{r.slug}{r.ok && r.ms != null ? <span className="opacity-70">{r.ms} ms</span> : null}
          </span>
        ))}
        {pulse.unreachable.map((slug) => (
          <span key={`u-${slug}`} className="rounded-pill bg-surface-2 px-2 py-0.5 text-muted" title={t("Kuncinya hanya dalam rahsia GitHub; disemak oleh api.yml setiap 6 jam", "Its key is only a GitHub secret; checked by api.yml every 6 hours")}>{slug} · api.yml</span>
        ))}
      </span>
      <Button type="button" size="sm" variant="ghost" onClick={check} disabled={busy} className="ml-auto">
        {busy ? <Loader2 size={13} className="animate-spin" /> : <RadioTower size={13} />} {busy ? t("Menyemak…", "Checking…") : t("Semak sekarang", "Check now")}
      </Button>
      {note && <p className="basis-full text-danger">{note}</p>}
    </div>
  );
}

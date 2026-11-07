import { useCallback, useEffect, useState } from "react";
import { Link2, RefreshCw, Send, Unlink } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import Card from "./ui/Card";

/* Semasa on Telegram (Wan, 7 Nov 2026; supabase/069, backend/semasa/telegram_bot.py). One Telegram account may command Semasa:
   the one that sends the bot a one-time code made here. The code lives 15 minutes and works once; only its hash is stored. */
export default function TelegramCard({ onToast }) {
  const { t } = useLang();
  const [st, setSt] = useState(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [missing, setMissing] = useState(false);

  const load = useCallback(async () => {
    const { data, error } = await supabase.rpc("semasa_telegram_status");
    if (error) { setMissing(/semasa_telegram_status|function/i.test(error.message)); return; }
    setMissing(false); setSt(data);
  }, []);
  useEffect(() => { load(); }, [load]);

  const makeCode = async () => {
    setBusy(true);
    const { data, error } = await supabase.rpc("semasa_telegram_link_code");
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    setCode(String(data || ""));
  };
  const unlink = async () => {
    setBusy(true);
    const { error } = await supabase.rpc("semasa_telegram_unlink");
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    setCode(""); onToast(t("Telegram diputuskan.", "Telegram unlinked."), "ok"); load();
  };

  const bot = st?.bot?.username ? `@${st.bot.username}` : t("bot anda", "your bot");
  return (
    <Card className="space-y-3 p-5" data-telegram>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg"><Send size={16} /> Telegram</h3>
          <p className="mt-1 text-[12px] text-muted">{t(
            "Kawal Semasa dari Telegram: /draf untuk lulus atau tolak draf, /jadual, /status, /ralat, /kesihatan, /bil, hantar link untuk jadikan idea, atau tanya apa-apa. Amaran watchdog juga dihantar ke sini.",
            "Run Semasa from Telegram: /draf to approve or reject drafts, /jadual, /status, /ralat, /kesihatan, /bil, send a link to make it an idea, or ask anything. Watchdog alerts come here too.")}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={load} aria-label={t("Muat semula", "Refresh")}><RefreshCw size={12} /></Button>
      </div>
      {missing ? (
        <p className="text-sm text-muted">{t("Jalankan supabase/069_telegram_bot.sql dahulu.", "Run supabase/069_telegram_bot.sql first.")}</p>
      ) : (
        <>
          <dl className="grid gap-1 text-sm sm:grid-cols-2">
            <div><dt className="text-[11px] uppercase text-muted">{t("Bot", "Bot")}</dt>
              <dd>{st?.bot?.username ? `@${st.bot.username}` : t("Belum disambung (aliran kerja Telegram belum berjalan)", "Not connected yet (the Telegram workflow has not run)")}</dd></div>
            <div><dt className="text-[11px] uppercase text-muted">Webhook</dt>
              <dd>{st?.bot?.webhook ? (st.bot.last_error ? `⚠️ ${st.bot.last_error}` : t("Hidup", "Live")) : "—"}</dd></div>
            <div><dt className="text-[11px] uppercase text-muted">{t("Akaun disambung", "Linked account")}</dt>
              <dd>{st?.linked ? `${st.username || t("(tiada nama)", "(no name)")} · ${stampMYT(st.linked_at)}` : t("Belum", "Not yet")}</dd></div>
            <div><dt className="text-[11px] uppercase text-muted">{t("Kumpulan dibaca (FAQ)", "Groups read (FAQ)")}</dt>
              <dd>{st?.groups ?? 0}{st?.waiting ? ` · ${st.waiting} ${t("mesej menunggu", "messages waiting")}` : ""}</dd></div>
          </dl>
          {code && (
            <p className="rounded-lg border border-line p-3 text-sm" data-telegram-code>
              {t("Hantar kepada", "Send to")} {bot} {t("dalam 15 minit:", "within 15 minutes:")} <b className="font-mono">/start {code}</b>
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={makeCode} disabled={busy}><Link2 size={12} /> {st?.linked ? t("Sambung akaun lain", "Link another account") : t("Jana kod", "Make a code")}</Button>
            {st?.linked && <Button size="sm" variant="ghost" onClick={unlink} disabled={busy}><Unlink size={12} /> {t("Putuskan", "Unlink")}</Button>}
          </div>
        </>
      )}
    </Card>
  );
}

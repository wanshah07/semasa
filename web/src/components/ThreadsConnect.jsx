import { useCallback, useEffect, useRef, useState } from "react";
import { AtSign, ExternalLink, KeyRound, Loader2, Plug, Power, Unplug } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { FIELD_ERRORS, STATE_CLS, STATE_WORDS, fieldProblem, needsApproval, stateOf } from "../lib/threadsConnect";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label } from "./ui/Field";

/* Wan's own Threads app (supabase/080, 13 Nov 2026). Composio's shared Threads app has no keyword-search permission ("Application
   does not have permission for this action"), so the Threads tab in Isu semasa stayed empty. Here Wan keeps his own app's Threads
   app ID, app secret and a long-lived user token; the worker (backend/semasa/threads_api.py) renews the token and reads public posts
   by keyword straight from Meta. This card shows a status and can never read the secret or the token back. */

export default function ThreadsConnect({ onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [status, setStatus] = useState(null);       // null while loading
  const [missing, setMissing] = useState(false);    // 080 not run
  const [appId, setAppId] = useState("");
  const [secret, setSecret] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState(false);
  const timer = useRef(null);

  const load = useCallback(async () => {
    const { data, error } = await supabase.rpc("semasa_threads_status");
    if (error) {
      if (/semasa_threads_status|PGRST202|42883|does not exist/i.test(`${error.code} ${error.message}`)) setMissing(true);
      else onToast?.(errText(error), "danger");
      return;
    }
    setMissing(false);
    setStatus(data || { connected: false });
  }, [onToast]);

  useEffect(() => { load(); return () => clearTimeout(timer.current); }, [load]);

  async function connect() {
    const bad = fieldProblem(appId, secret, token);
    if (bad) return onToast?.(FIELD_ERRORS[bad][L], "warn");
    setBusy("connect");
    const { data, error } = await supabase.rpc("semasa_threads_connect", { p_app_id: appId.trim(), p_app_secret: secret.trim(), p_token: token.trim() });
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    setAppId(""); setSecret(""); setToken("");      // the secret and the token leave this page the moment they are saved
    setStatus(data);
    onToast?.(t("Threads disimpan. Larian Sources seterusnya menyemaknya.", "Threads saved. The next Sources run checks it."), "ok");
  }

  async function toggle() {
    setBusy("set");
    const { data, error } = await supabase.rpc("semasa_threads_set", { p_enabled: status?.enabled === false });
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    setStatus(data);
  }

  async function disconnect() {
    if (!sure) { setSure(true); timer.current = setTimeout(() => setSure(false), 6000); return; }
    setBusy("off");
    const { error } = await supabase.rpc("semasa_threads_disconnect");
    setBusy("");
    setSure(false);
    if (error) return onToast?.(errText(error), "danger");
    setStatus({ connected: false });
    onToast?.(t("Threads diputuskan dan rahsia serta token dipadam.", "Threads disconnected and the secret and token deleted."), "ok");
  }

  if (missing) {
    return (
      <Card className="mb-4 p-4 text-sm text-muted" data-threads-connect>
        <h3 className="flex items-center gap-2 text-base text-ink"><AtSign size={16} className="text-accent" /> {t("Aplikasi Threads sendiri", "Own Threads app")}</h3>
        <p className="mt-1">{t("Jalankan supabase/080_threads_auth.sql sekali dahulu.", "Run supabase/080_threads_auth.sql once first.")}</p>
      </Card>
    );
  }

  const state = stateOf(status);
  const word = (k) => STATE_WORDS[k][L];

  return (
    <Card className="mb-4 space-y-3 p-4" data-threads-connect>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 text-base"><AtSign size={16} className="text-accent" /> {t("Aplikasi Threads sendiri (pos tular)", "Own Threads app (viral posts)")}</h3>
        {status && <span className={`rounded-pill px-2 py-0.5 text-xs ${STATE_CLS[state]}`} data-threads-state={state}>{word(state)}</span>}
      </div>
      <p className="max-w-2xl text-xs text-muted">
        {t("Tab Threads dalam Isu semasa membaca pos Threads yang tular. Aplikasi kongsi Composio tidak mendapat kebenaran carian kata kunci, jadi aplikasi anda sendiri digunakan. Tanpa kelulusan Meta untuk threads_keyword_search, Threads hanya mencari pos akaun anda sendiri, dan tiada baris dibuat daripadanya.",
          "The Threads tab in Isu semasa reads viral Threads posts. Composio's shared app has no keyword-search permission, so your own app is used. Without Meta's approval of threads_keyword_search, Threads searches only your own account's posts, and no row is made from those.")}
      </p>

      {status === null && <p className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> {t("Memuatkan…", "Loading…")}</p>}

      {status && !status.connected && (
        <div className="space-y-3">
          <ol className="list-decimal space-y-0.5 pl-5 text-xs text-muted">
            <li>{t("Di", "At")} <a className="inline-flex items-center gap-0.5 text-accent underline" href="https://developers.facebook.com/apps/" target="_blank" rel="noreferrer">developers.facebook.com/apps <ExternalLink size={10} /></a> {t("buka aplikasi anda, kemudian Use cases, Access the Threads API, Settings: salin Threads app ID dan Threads app secret (Show).", "open your app, then Use cases, Access the Threads API, Settings: copy the Threads app ID and Threads app secret (Show).")}</li>
            <li>{t("Jana token pengguna Threads dengan threads_basic dan threads_keyword_search (Graph API Explorer boleh digunakan semasa menguji), dan tukarkannya kepada token tahan lama (60 hari) menggunakan rahsia di atas.", "Generate a Threads user token with threads_basic and threads_keyword_search (the Graph API Explorer works while testing) and exchange it for a long-lived token (60 days) using the secret above.")}</li>
            <li>{t("Tampal ketiga-tiganya di bawah. Semasa memperbaharui token sendiri sebelum tamat.", "Paste all three below. Semasa renews the token itself before it ends.")}</li>
          </ol>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block"><Label>{t("Threads app ID", "Threads app ID")}</Label>
              <Input value={appId} onChange={(e) => setAppId(e.target.value)} inputMode="numeric" autoComplete="off" spellCheck={false} aria-label="Threads app ID" /></label>
            <label className="block"><Label hint={t("disimpan di tempat halaman ini tidak boleh baca semula", "kept where this page can never read it back")}>{t("Threads app secret", "Threads app secret")}</Label>
              <Input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="off" spellCheck={false} aria-label="Threads app secret" /></label>
            <label className="block sm:col-span-2"><Label hint={t("disimpan di tempat halaman ini tidak boleh baca semula", "kept where this page can never read it back")}>{t("Token tahan lama", "Long-lived token")}</Label>
              <Input type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off" spellCheck={false} aria-label="Long-lived Threads token" /></label>
          </div>
          <Button size="sm" onClick={connect} disabled={busy === "connect" || !appId.trim() || !secret.trim() || !token.trim()} data-threads-save>
            {busy === "connect" ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />} {t("Sambung Threads", "Connect Threads")}
          </Button>
        </div>
      )}

      {status?.connected && (
        <div className="space-y-3">
          <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            <div><dt className="inline text-muted">App ID: </dt><dd className="inline">{status.app_id}</dd></div>
            <div><dt className="inline text-muted">{t("Akaun", "Account")}: </dt><dd className="inline">{status.username ? `@${status.username}` : t("belum disemak", "not checked yet")}</dd></div>
            <div><dt className="inline text-muted">{t("Token tamat", "Token ends")}: </dt><dd className="inline">{status.expires_at ? timeAgo(status.expires_at) : "—"}</dd></div>
            <div><dt className="inline text-muted">{t("Berjaya kali akhir", "Last success")}: </dt><dd className="inline">{status.last_ok_at ? timeAgo(status.last_ok_at) : t("belum", "not yet")}</dd></div>
            {status.last_error && (
              <div className="sm:col-span-2"><dt className="inline text-danger">{t("Ralat terakhir", "Last error")} ({timeAgo(status.last_error_at)}): </dt><dd className="inline break-words" data-threads-error>{status.last_error}</dd></div>
            )}
          </dl>
          {needsApproval(status) && (
            <p className="text-xs text-warn" data-threads-approval>
              {t("Langkah seterusnya: mohon kelulusan threads_keyword_search di App Review Meta. Selagi belum diluluskan, hanya pos akaun anda boleh dicari.", "Next step: request threads_keyword_search in Meta's App Review. Until it is approved, only your own account's posts can be searched.")}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={status.enabled === false ? "primary" : "ghost"} onClick={toggle} disabled={busy === "set"}>
              <Power size={13} /> {status.enabled === false ? t("Hidupkan", "Switch on") : t("Matikan", "Switch off")}
            </Button>
            <Button size="sm" variant="danger" onClick={disconnect} disabled={busy === "off"}>
              <Unplug size={13} /> {sure ? t("Pasti? Klik sekali lagi", "Sure? Click again") : t("Putuskan", "Disconnect")}
            </Button>
          </div>
          <p className="flex items-start gap-1 text-xs text-muted"><KeyRound size={12} className="mt-0.5 shrink-0" /> {t("Rahsia dan token tidak boleh dibaca semula oleh halaman ini. Untuk menukar aplikasi, putuskan dan tampal yang baharu.", "This page can never read the secret or the token back. To change app, disconnect and paste new ones.")}</p>
        </div>
      )}
    </Card>
  );
}

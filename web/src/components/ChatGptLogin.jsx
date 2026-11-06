import { useCallback, useEffect, useRef, useState } from "react";
import { ImagePlus, KeyRound, Loader2, Plug, Power, Save, Unplug } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { DEFAULT_MODEL, MAX_IMAGES, PARSE_ERRORS, STATE_CLS, STATE_WORDS, parseAuth, stateOf, validModel } from "../lib/chatgptLogin";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label, TextArea } from "./ui/Field";

/* Motion draws a picture for each scene of its storyboard through Wan's ChatGPT login (Wan, 5 Nov 2026). He runs `codex login`
   once on his own computer and pastes ~/.codex/auth.json here. supabase/058 keeps it where this page can never read it back; the
   worker refreshes it and draws. This card shows only a status, and the switch, the model and how many pictures a film may draw. */

export default function ChatGptLogin({ onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [status, setStatus] = useState(null);       // null while loading
  const [missing, setMissing] = useState(false);    // 058 not run
  const [paste, setPaste] = useState("");
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [maxImages, setMaxImages] = useState(6);
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState(false);
  const timers = useRef([]);

  const load = useCallback(async () => {
    const { data, error } = await supabase.rpc("semasa_chatgpt_status");
    if (error) {
      if (/semasa_chatgpt_status|PGRST202|42883|does not exist/i.test(`${error.code} ${error.message}`)) setMissing(true);
      else onToast?.(errText(error), "danger");
      return;
    }
    setMissing(false);
    setStatus(data || { connected: false });
    if (data?.connected) { setModel(data.model || DEFAULT_MODEL); setMaxImages(data.max_images || 6); }
  }, [onToast]);

  useEffect(() => { load(); return () => timers.current.forEach(clearTimeout); }, [load]);

  const state = stateOf(status);
  const word = (s) => STATE_WORDS[s][L];

  async function connect() {
    const got = parseAuth(paste);
    if (!got.ok) return onToast?.(PARSE_ERRORS[got.code][L], "warn");
    setBusy("connect");
    const { data, error } = await supabase.rpc("semasa_chatgpt_connect", { p_auth: got.auth, p_account: got.account, p_expires: got.expires });
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    setPaste("");                                   // the tokens leave this page the moment they are saved
    setStatus(data);
    onToast?.(t("ChatGPT disambung. Semasa sedang menyemaknya sekarang.", "ChatGPT connected. Semasa is checking it now."), "ok");
    // the database wakes the API check, which refreshes the token and writes the result: look again when it should be done
    timers.current.push(setTimeout(load, 30_000), setTimeout(load, 80_000));
  }

  async function save(enabled) {
    if (!validModel(model)) return onToast?.(t("Nama model: huruf, nombor dan . _ : - sahaja.", "Model name: letters, digits and . _ : - only."), "warn");
    setBusy("save");
    const { data, error } = await supabase.rpc("semasa_chatgpt_set", { p_enabled: enabled, p_model: model.trim(), p_max: Number(maxImages) });
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    setStatus(data);
    onToast?.(t("Disimpan. Video seterusnya menggunakannya.", "Saved. The next film uses it."), "ok");
  }

  async function disconnect() {
    if (!sure) { setSure(true); timers.current.push(setTimeout(() => setSure(false), 6000)); return; }
    setBusy("off");
    const { error } = await supabase.rpc("semasa_chatgpt_disconnect");
    setBusy("");
    setSure(false);
    if (error) return onToast?.(errText(error), "danger");
    setStatus({ connected: false });
    onToast?.(t("ChatGPT diputuskan dan token dipadam.", "ChatGPT disconnected and the tokens deleted."), "ok");
  }

  if (missing) {
    return (
      <Card className="mb-4 p-4 text-sm text-muted" data-chatgpt-login>
        <h3 className="flex items-center gap-2 text-base text-ink"><ImagePlus size={16} className="text-accent" /> {t("Gambar ChatGPT", "ChatGPT pictures")}</h3>
        <p className="mt-1">{t("Jalankan supabase/058_chatgpt_login.sql sekali dahulu.", "Run supabase/058_chatgpt_login.sql once first.")}</p>
      </Card>
    );
  }

  return (
    <Card className="mb-4 space-y-3 p-4" data-chatgpt-login>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 text-base"><ImagePlus size={16} className="text-accent" /> {t("Gambar ChatGPT untuk setiap babak", "ChatGPT pictures for every scene")}</h3>
        {status && <span className={`rounded-pill px-2 py-0.5 text-xs ${STATE_CLS[state]}`} data-chatgpt-state={state}>{word(state)}</span>}
      </div>
      <p className="max-w-2xl text-xs text-muted">
        {t("Setiap babak papan cerita dilukis satu gambar mengikut gaya video, menggunakan log masuk ChatGPT anda. Babak yang gagal kekal dengan foto Unsplash; video tetap siap.",
          "Each scene of the storyboard gets a picture drawn in the film's style, using your ChatGPT login. A scene that fails keeps its Unsplash photo; the film is still made.")}
      </p>

      {status === null && <p className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> {t("Memuatkan…", "Loading…")}</p>}

      {status && !status.connected && (
        <div className="space-y-2">
          <ol className="list-decimal space-y-0.5 pl-5 text-xs text-muted">
            <li>{t("Di komputer anda, jalankan", "On your computer, run")} <code className="rounded bg-surface-2 px-1">codex login</code> {t("dan pilih Sign in with ChatGPT.", "and choose Sign in with ChatGPT.")}</li>
            <li>{t("Buka fail", "Open the file")} <code className="rounded bg-surface-2 px-1">~/.codex/auth.json</code> {t("(Windows: %USERPROFILE%\\.codex\\auth.json).", "(Windows: %USERPROFILE%\\.codex\\auth.json).")}</li>
            <li>{t("Salin seluruh kandungannya dan tampal di bawah.", "Copy all of it and paste it below.")}</li>
          </ol>
          <label className="block"><Label hint={t("disimpan di tempat yang halaman ini tidak boleh baca semula", "kept where this page can never read it back")}>auth.json</Label>
            <TextArea rows={4} value={paste} onChange={(e) => setPaste(e.target.value)} spellCheck={false} autoComplete="off"
              placeholder='{"tokens": {"access_token": "…", "refresh_token": "…"}}' className="font-mono text-xs" /></label>
          <Button size="sm" onClick={connect} disabled={busy === "connect" || !paste.trim()}>
            {busy === "connect" ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />} {t("Sambung ChatGPT", "Connect ChatGPT")}
          </Button>
          <p className="text-xs text-muted">{t("Ini log masuk Codex OpenAI sendiri, bukan API rasmi: OpenAI boleh mengubah atau menghadkannya tanpa notis.", "This is OpenAI's own Codex login, not an official API: OpenAI can change or limit it without notice.")}</p>
        </div>
      )}

      {status?.connected && (
        <div className="space-y-3">
          <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
            <div><dt className="inline text-muted">{t("Akaun", "Account")}: </dt><dd className="inline">{status.account || "—"}</dd></div>
            <div><dt className="inline text-muted">{t("Token tamat", "Token ends")}: </dt><dd className="inline">{status.access_expires_at ? timeAgo(status.access_expires_at) : "—"}</dd></div>
            <div><dt className="inline text-muted">{t("Berjaya kali akhir", "Last success")}: </dt><dd className="inline">{status.last_ok_at ? timeAgo(status.last_ok_at) : t("belum", "not yet")}</dd></div>
            {status.last_error && (
              <div className="sm:col-span-2"><dt className="inline text-danger">{t("Ralat terakhir", "Last error")} ({timeAgo(status.last_error_at)}): </dt><dd className="inline break-words" data-chatgpt-error>{status.last_error}</dd></div>
            )}
          </dl>
          <div className="flex flex-wrap items-end gap-3">
            <label className="block"><Label>{t("Model", "Model")}</Label>
              <Input value={model} onChange={(e) => setModel(e.target.value)} className="w-40" aria-label="Model" /></label>
            <label className="block"><Label>{t("Gambar paling banyak setiap video", "Most pictures a film")}</Label>
              <select value={maxImages} onChange={(e) => setMaxImages(e.target.value)} aria-label={t("Gambar paling banyak", "Most pictures")}
                className="rounded-pill border border-line bg-surface px-3 py-2 text-xs">{MAX_IMAGES.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
            <Button size="sm" variant="soft" onClick={() => save(status.enabled !== false)} disabled={busy === "save"}><Save size={13} /> {t("Simpan", "Save")}</Button>
            <Button size="sm" variant={status.enabled === false ? "primary" : "ghost"} onClick={() => save(status.enabled === false)} disabled={busy === "save"}>
              <Power size={13} /> {status.enabled === false ? t("Hidupkan", "Switch on") : t("Matikan", "Switch off")}
            </Button>
            <Button size="sm" variant="danger" onClick={disconnect} disabled={busy === "off"}>
              <Unplug size={13} /> {sure ? t("Pasti? Klik sekali lagi", "Sure? Click again") : t("Putuskan", "Disconnect")}
            </Button>
          </div>
          <p className="flex items-start gap-1 text-xs text-muted"><KeyRound size={12} className="mt-0.5 shrink-0" /> {t("Token tidak boleh dibaca semula oleh halaman ini. Untuk menukar akaun, putuskan dan tampal auth.json baharu.", "This page can never read the tokens back. To change account, disconnect and paste a new auth.json.")}</p>
        </div>
      )}
    </Card>
  );
}

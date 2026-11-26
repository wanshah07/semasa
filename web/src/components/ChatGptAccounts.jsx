import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Copy, ExternalLink, Loader2, Power, RefreshCw, Trash2, UserPlus, Users, X } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { POLL_MS, clock, deviceView, forTarget, polling } from "../lib/chatgptDevice";
import { ACCOUNT_CLS, ACCOUNT_WORDS, MAX_ACCOUNTS, REASONING, accountState, canAdd, ordered, restMinutes, restText, usable, validReasoning } from "../lib/chatgptAccounts";
import { DEFAULT_MODEL, MAX_IMAGES, validModel } from "../lib/chatgptLogin";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label } from "./ui/Field";

/* More than one ChatGPT account for pictures (Wan, 24 Nov 2026: "add chatgpt segment that I can add multiple accounts to support
   image gen using chatgpt"). One ChatGPT plan draws only so many pictures before it answers "usage limit". The accounts added
   here (supabase/095) are used for PICTURES only: the worker asks the main login first, then each of these in order, and an
   account that says its allowance is used up rests for three hours while the next one draws.

   An account is added with the same link-and-code login as the main one; the request says it is for a new account, so the main
   login is never overwritten. This card can never read a token back: it sees the e-mail, the switch, the last success, the last
   error and when a resting account is asked again. */

export default function ChatGptAccounts({ onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [rows, setRows] = useState(null);           // null while loading
  const [missing, setMissing] = useState(false);    // 095 not run
  const [dev, setDev] = useState(null);             // this card's own code request (target "new")
  const [skew, setSkew] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState("");             // the id whose Remove was clicked once
  const [edits, setEdits] = useState({});           // id -> {model, reasoning, max} typed but not saved yet
  const timers = useRef([]);
  const lastPhase = useRef("idle");

  const load = useCallback(async () => {
    const { data, error } = await supabase.rpc("semasa_chatgpt_accounts_status");
    if (error) {
      if (/semasa_chatgpt_accounts_status|PGRST202|42883|does not exist/i.test(`${error.code} ${error.message}`)) setMissing(true);
      else onToast?.(errText(error), "danger");
      return;
    }
    setMissing(false);
    setRows(ordered(data));
  }, [onToast]);

  const readDevice = useCallback((data) => {
    setDev(forTarget(data, "new"));
    const server = Date.parse(data?.server_now || "");
    if (Number.isFinite(server)) setSkew(server - Date.now());
  }, []);

  const loadDevice = useCallback(async () => {
    const { data, error } = await supabase.rpc("semasa_chatgpt_device_status");
    if (!error) readDevice(data);
  }, [readDevice]);

  useEffect(() => { load(); loadDevice(); return () => timers.current.forEach(clearTimeout); }, [load, loadDevice]);

  const view = deviceView(dev, now, skew);
  const live = polling(view);

  useEffect(() => {
    if (!live) return undefined;
    const ask = setInterval(loadDevice, POLL_MS);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(ask); clearInterval(tick); };
  }, [live, loadDevice]);

  // a resting account's countdown moves by the minute
  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(tick);
  }, []);

  // the approval arrived: the worker saved the account and marked the request done
  useEffect(() => {
    if (view.phase === "done" && (lastPhase.current === "waiting" || lastPhase.current === "requested")) {
      load();
      onToast?.(t("Akaun ChatGPT ditambah untuk gambar.", "ChatGPT account added for pictures."), "ok");
    }
    lastPhase.current = view.phase;
  }, [view.phase, load, onToast, t]);

  async function add() {
    setBusy("add");
    setCopied(false);
    const { data, error } = await supabase.rpc("semasa_chatgpt_account_start");
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    setNow(Date.now());
    readDevice(data);
  }

  async function cancel() {
    setBusy("add");
    const { data, error } = await supabase.rpc("semasa_chatgpt_device_cancel");
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    readDevice(data);
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(view.code);
      setCopied(true);
      timers.current.push(setTimeout(() => setCopied(false), 2500));
    } catch { onToast?.(t("Salin sendiri: ", "Copy it yourself: ") + view.code, "warn"); }
  }

  // the switch, and "ask it again now" (saving the switch as it is ends a rest)
  async function set(row, enabled, said) {
    setBusy(row.id);
    const { data, error } = await supabase.rpc("semasa_chatgpt_account_set", { p_id: row.id, p_enabled: enabled });
    setBusy("");
    if (error) return onToast?.(errText(error), "danger");
    setRows(ordered(data));
    onToast?.(said, "ok");
  }

  // an account's own model, reasoning effort and pictures a film (supabase/098)
  const draft = (r) => ({ model: r.model || DEFAULT_MODEL, reasoning: r.reasoning || "", max: String(r.max_images || 6), ...(edits[r.id] || {}) });
  const edit = (r, patch) => setEdits((e) => ({ ...e, [r.id]: { ...draft(r), ...patch } }));
  async function saveConfig(r) {
    const d = draft(r);
    if (!validModel(d.model)) return onToast?.(t("Nama model: huruf, nombor dan . _ : - sahaja.", "Model name: letters, digits and . _ : - only."), "warn");
    if (!validReasoning(d.reasoning)) return onToast?.(t("Tahap reasoning tidak dikenali.", "Unknown reasoning effort."), "warn");
    setBusy(r.id);
    const { data, error } = await supabase.rpc("semasa_chatgpt_account_config",
      { p_id: r.id, p_model: d.model.trim(), p_reasoning: d.reasoning, p_max: Number(d.max) });
    setBusy("");
    if (error) {
      if (/semasa_chatgpt_account_config|PGRST202|42883/i.test(`${error.code} ${error.message}`)) return onToast?.(t("Jalankan supabase/098_chatgpt_account_config.sql sekali dahulu.", "Run supabase/098_chatgpt_account_config.sql once first."), "warn");
      return onToast?.(errText(error), "danger");
    }
    setRows(ordered(data));
    setEdits((e) => { const { [r.id]: _gone, ...rest } = e; return rest; });
    onToast?.(t("Disimpan. Gambar seterusnya menggunakannya.", "Saved. The next picture uses it."), "ok");
  }

  async function remove(row) {
    if (sure !== row.id) { setSure(row.id); timers.current.push(setTimeout(() => setSure(""), 6000)); return; }
    setBusy(row.id);
    const { data, error } = await supabase.rpc("semasa_chatgpt_account_remove", { p_id: row.id });
    setBusy("");
    setSure("");
    if (error) return onToast?.(errText(error), "danger");
    setRows(ordered(data));
    onToast?.(t("Akaun dibuang dan tokennya dipadam.", "Account removed and its tokens deleted."), "ok");
  }

  const head = (
    <h3 className="flex items-center gap-2 text-base"><Users size={16} className="text-accent" /> {t("Akaun ChatGPT tambahan untuk gambar", "Extra ChatGPT accounts for pictures")}</h3>
  );

  if (missing) {
    return (
      <Card className="mb-4 scroll-mt-20 p-4 text-sm text-muted" id="chatgpt-accounts" data-chatgpt-accounts="missing">
        {head}
        <p className="mt-1">{t("Jalankan supabase/095_chatgpt_accounts.sql sekali dahulu.", "Run supabase/095_chatgpt_accounts.sql once first.")}</p>
      </Card>
    );
  }

  const list = rows || [];
  const showPanel = ["requested", "waiting", "expired", "error"].includes(view.phase);

  return (
    <Card className="mb-4 scroll-mt-20 space-y-3 p-4" id="chatgpt-accounts" data-chatgpt-accounts>
      <div className="flex flex-wrap items-center gap-2">
        {head}
        {rows && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-xs text-muted" data-chatgpt-accounts-count>
          {list.length}/{MAX_ACCOUNTS} · {usable(list, now)} {t("boleh melukis sekarang", "can draw now")}
        </span>}
      </div>
      <p className="max-w-2xl text-xs text-muted">
        {t("Satu pelan ChatGPT hanya melukis sejumlah gambar sebelum menjawab “usage limit”. Tambah akaun ChatGPT lain di sini: log masuk utama ditanya dahulu, kemudian setiap akaun mengikut turutan. Akaun yang hadnya habis berehat 3 jam dan akaun seterusnya terus melukis. Untuk gambar sahaja; penulisan dan sembang kekal dengan log masuk utama. Suis “Matikan” pada kad di atas mematikan semuanya.",
          "One ChatGPT plan draws only so many pictures before it answers “usage limit”. Add other ChatGPT accounts here: the main login is asked first, then each account in order. An account whose allowance is used up rests for 3 hours and the next one keeps drawing. For pictures only; writing and chat stay with the main login. The “Switch off” on the card above turns all of them off.")}
      </p>

      {rows === null && <p className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> {t("Memuatkan…", "Loading…")}</p>}

      {rows && list.length === 0 && !showPanel && (
        <p className="text-xs text-muted" data-chatgpt-accounts-empty>{t("Belum ada akaun tambahan. Hanya log masuk utama yang melukis.", "No extra account yet. Only the main login draws.")}</p>
      )}

      {list.length > 0 && (
        <ul className="divide-y divide-line rounded-tile border border-line" data-chatgpt-accounts-list>
          {list.map((r, i) => {
            const state = accountState(r, now);
            const mins = restMinutes(r, now);
            return (
              <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3 text-xs" data-chatgpt-account={r.id} data-state={state}>
                <span className="w-5 shrink-0 text-center font-mono text-muted" title={t("Turutan ditanya (selepas log masuk utama)", "Order asked (after the main login)")}>{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2">
                    <b className="break-all text-sm font-medium text-ink">{r.account || r.id}</b>
                    <span className={`rounded-pill px-2 py-0.5 ${ACCOUNT_CLS[state]}`}>{ACCOUNT_WORDS[state][L]}</span>
                    {state === "resting" && <span className="text-warn" data-chatgpt-rest>{t("ditanya semula dalam", "asked again in")} {restText(mins, L === 1)}</span>}
                  </p>
                  <p className="mt-0.5 text-muted">
                    {t("Melukis kali akhir", "Last drew")}: {r.last_ok_at ? timeAgo(r.last_ok_at) : t("belum", "not yet")}
                    {r.connected_at && <> · {t("ditambah", "added")} {timeAgo(r.connected_at)}</>}
                  </p>
                  {r.last_error && state !== "ok" && state !== "ready" && (
                    <p className={`mt-0.5 break-words ${state === "error" ? "text-danger" : "text-muted"}`} data-chatgpt-account-error>
                      {r.last_error_at ? `${timeAgo(r.last_error_at)}: ` : ""}{String(r.last_error).slice(0, 300)}
                    </p>
                  )}
                </div>
                <div className="flex w-full flex-wrap items-end gap-3 border-t border-line/60 pt-2" data-chatgpt-account-config={r.id}>
                  <label className="block"><Label>{t("Model", "Model")}</Label>
                    <Input value={draft(r).model} onChange={(e) => edit(r, { model: e.target.value })} className="w-40" aria-label={t("Model", "Model")} /></label>
                  <label className="block"><Label>{t("Reasoning", "Reasoning")}</Label>
                    <select value={draft(r).reasoning} onChange={(e) => edit(r, { reasoning: e.target.value })} aria-label="Reasoning"
                      className="rounded-pill border border-line bg-surface px-3 py-2 text-xs">{REASONING.map(([k, w]) => <option key={k} value={k}>{w[L]}</option>)}</select></label>
                  <label className="block"><Label>{t("Gambar paling banyak setiap video", "Most pictures a film")}</Label>
                    <select value={draft(r).max} onChange={(e) => edit(r, { max: e.target.value })} aria-label={t("Gambar paling banyak", "Most pictures")}
                      className="rounded-pill border border-line bg-surface px-3 py-2 text-xs">{MAX_IMAGES.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
                  <Button size="sm" variant="soft" disabled={busy === r.id || !edits[r.id]} onClick={() => saveConfig(r)}>{t("Simpan", "Save")}</Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {state === "resting" && (
                    <Button size="sm" variant="soft" disabled={busy === r.id}
                      onClick={() => set(r, r.enabled !== false, t("Rehat ditamatkan. Akaun ini ditanya semula pada gambar seterusnya.", "Rest ended. This account is asked again on the next picture."))}>
                      <RefreshCw size={13} /> {t("Tanya semula sekarang", "Ask again now")}
                    </Button>
                  )}
                  <Button size="sm" variant={r.enabled === false ? "primary" : "ghost"} disabled={busy === r.id}
                    onClick={() => set(r, r.enabled === false, r.enabled === false ? t("Dihidupkan.", "Switched on.") : t("Dimatikan. Akaun ini tidak ditanya.", "Switched off. This account is not asked."))}>
                    <Power size={13} /> {r.enabled === false ? t("Hidupkan", "Switch on") : t("Matikan", "Switch off")}
                  </Button>
                  <Button size="sm" variant="danger" disabled={busy === r.id} onClick={() => remove(r)}>
                    <Trash2 size={13} /> {sure === r.id ? t("Pasti? Klik sekali lagi", "Sure? Click again") : t("Buang", "Remove")}
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {showPanel && (
        <div className="space-y-3 rounded-tile border border-line bg-surface-2/60 p-3" data-chatgpt-account-device={view.phase}>
          {view.phase === "requested" && (
            <>
              <p className="flex items-center gap-2 text-sm"><Loader2 size={14} className="animate-spin" /> {t("Meminta kod daripada OpenAI… biasanya kira-kira satu minit.", "Asking OpenAI for a code… usually about a minute.")}</p>
              {view.stalled && <p className="text-xs text-warn">{t("Belum dimulakan oleh pelayan. Semak tab Actions di GitHub (ChatGPT login) atau token Vault, kemudian tekan Kod baharu.", "The worker has not started. Check the Actions tab on GitHub (ChatGPT login) or the Vault token, then press New code.")}</p>}
            </>
          )}
          {view.phase === "waiting" && (
            <>
              <ol className="list-decimal space-y-2 pl-5 text-sm">
                <li><b>{t("Guna tetingkap peribadi (Incognito).", "Use a private (Incognito) window.")}</b> {t("Pelayar biasa anda sudah log masuk dengan akaun utama, dan akaun yang sama akan ditolak.", "Your normal browser is already signed in with the main account, and the same account is refused.")}</li>
                <li>{t("Buka pautan ini dan log masuk dengan akaun ChatGPT YANG LAIN:", "Open this link and sign in with the OTHER ChatGPT account:")}{" "}
                  <a href={view.url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-accent underline underline-offset-2">auth.openai.com/codex/device <ExternalLink size={12} /></a></li>
                <li>{t("Masukkan kod sekali guna ini:", "Enter this one-time code:")}
                  <span className="mt-1 flex flex-wrap items-center gap-2">
                    <code className="rounded-tile bg-bg px-3 py-1.5 font-mono text-xl tracking-widest" data-chatgpt-account-code>{view.code}</code>
                    <Button size="sm" variant="soft" onClick={copyCode}>{copied ? <Check size={13} /> : <Copy size={13} />} {copied ? t("Disalin", "Copied") : t("Salin", "Copy")}</Button>
                  </span></li>
                <li>{t("Selepas anda luluskan, akaun itu muncul dalam senarai di atas.", "After you approve it, the account appears in the list above.")}</li>
              </ol>
              <p className="flex items-center gap-2 text-xs text-muted"><Loader2 size={12} className="animate-spin" /> {t("Menunggu kelulusan", "Waiting for approval")} · {t("kod tamat dalam", "the code ends in")} <b>{clock(view.secondsLeft)}</b></p>
            </>
          )}
          {view.phase === "expired" && <p className="text-sm text-warn">{t("Kod itu sudah tamat (15 minit). Minta kod baharu.", "That code has expired (15 minutes). Ask for a new one.")}</p>}
          {view.phase === "error" && <p className="text-sm text-danger break-words" data-chatgpt-account-device-error>{view.error || t("Log masuk gagal.", "The login failed.")}</p>}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant={live ? "ghost" : "primary"} onClick={add} disabled={busy === "add"}><RefreshCw size={13} /> {t("Kod baharu", "New code")}</Button>
            {live && <Button size="sm" variant="ghost" onClick={cancel} disabled={busy === "add"}><X size={13} /> {t("Batal", "Cancel")}</Button>}
          </div>
        </div>
      )}

      {rows && !showPanel && (
        canAdd(list)
          ? <Button size="sm" onClick={add} disabled={busy === "add"} data-chatgpt-account-add>
              {busy === "add" ? <Loader2 size={13} className="animate-spin" /> : <UserPlus size={13} />} {t("Tambah akaun ChatGPT", "Add a ChatGPT account")}
            </Button>
          : <p className="text-xs text-muted">{t(`Paling banyak ${MAX_ACCOUNTS} akaun tambahan. Buang satu untuk menambah yang lain.`, `${MAX_ACCOUNTS} extra accounts is the most. Remove one to add another.`)}</p>
      )}
      <p className="text-xs text-muted">{t("Halaman ini tidak boleh membaca semula token. Log masuk semula dengan akaun yang sama membaiki barisnya, tidak menambah baris baharu.", "This page can never read the tokens back. Logging in again with the same account repairs its row; it does not add a new one.")}</p>
    </Card>
  );
}

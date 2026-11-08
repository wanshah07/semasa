import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Bot, CheckCircle2, Eye, EyeOff, KeyRound, Loader2, Pencil, Plus, Power, Save, Trash2, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { fmtMs } from "../lib/aiTeam";
import {
  DIALECTS, DOT_CLS, JOB_CHOICES, MAX_PROVIDERS, STATE_CLS, STATE_WORDS, formOf, formProblem, hostOf, keyWillDrop, numbered, providerState,
  rpcArgs, slugOf, toggleJob,
} from "../lib/aiProviders";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label, Select, TextArea } from "./ui/Field";

/* Extra AI providers (Wan, Nov 2026): an Anthropic key, a second KiosAPI key, any OpenAI-compatible gateway, added here and used by
   the whole backend as robots Wanshah 6, 7, ... (supabase/074, backend/semasa/ai_providers.py). The page sees the slug, name, dialect,
   host, model and the key's last four characters, never the key; the state dot is the probe's own row (semasa_api_status), read by
   ApiTab and passed in. Gemini stays on its own card: its keys are picked automatically there. */

export default function AiProviders({ statusRows = [], usageRows = [], onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const table = useTable(TABLES.aiProviders, { enabled: true, order: "created_at", ascending: true, limit: 50, everyMs: 120_000 });
  const rows = useMemo(() => numbered(table.rows), [table.rows]);
  const status = useMemo(() => Object.fromEntries((statusRows || []).map((r) => [r.slug, r])), [statusRows]);
  const missing = /semasa_ai_providers|does not exist|42P01|PGRST205/i.test(table.error || "");
  const [open, setOpen] = useState(false);            // the form is shown
  const [editing, setEditing] = useState(null);       // the row being edited, or null for a new one
  const [form, setForm] = useState(formOf(null));
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState("");
  const [msg, setMsg] = useState(null);               // {kind: "ok" | "err" | "info", text}: stays until the next action
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 60_000); return () => clearInterval(id); }, []);

  function startNew() { setEditing(null); setForm(formOf(null)); setShow(false); setMsg(null); setOpen(true); }
  function startEdit(r) { setEditing(r); setForm(formOf(r)); setShow(false); setMsg(null); setOpen(true); }
  function close() { setOpen(false); setEditing(null); setMsg(null); }

  async function rpc(name, args) {
    setBusy(name + (args.p_id || ""));
    const { data, error } = await supabase.rpc(name, args);
    setBusy("");
    if (error) {
      const text = errText(error);
      setMsg({ kind: "err", text });
      onToast?.(text, "danger");
      return null;
    }
    return data ?? true;
  }

  async function saveForm() {
    const bad = formProblem(form, { existing: editing, rows });
    if (bad) { setMsg({ kind: "err", text: bad[L] }); return; }
    setMsg({ kind: "info", text: t("Menyimpan…", "Saving…") });
    const data = await rpc("semasa_save_ai_provider", rpcArgs(form));
    if (!data) return;
    await table.reload?.();
    const dropped = data?.key_dropped;
    onToast?.(t("Disimpan.", "Saved."), "ok");
    setMsg({ kind: "ok", text: dropped
      ? t("Disimpan. Endpoint berpindah hos, jadi kunci lama DIGUGURKAN: tampal kunci untuk hos baharu.", "Saved. The endpoint moved to another host, so the old key was DROPPED: paste a key for the new host.")
      : t("Disimpan. Semakan API seterusnya (setiap 6 jam, atau Run workflow di GitHub) menanya robot ini; larian selepas itu boleh menggunakannya.",
        "Saved. The next API check (every 6 hours, or Run workflow on GitHub) asks this robot; runs after that may use it.") });
    setOpen(false); setEditing(null);
  }

  async function toggle(r) {
    setMsg(null);
    const f = { ...formOf(r), enabled: r.enabled === false };
    if (await rpc("semasa_save_ai_provider", rpcArgs(f))) {
      await table.reload?.();
      onToast?.(f.enabled ? t("Dihidupkan.", "Switched on.") : t("Dimatikan.", "Switched off."), "ok");
    }
  }

  async function remove(r) {
    if (sure !== r.id) { setSure(r.id); setTimeout(() => setSure(""), 6000); return; }
    setSure(""); setMsg(null);
    if (await rpc("semasa_delete_ai_provider", { p_id: r.id })) {
      await table.reload?.();
      onToast?.(t("Penyedia dipadam.", "Provider deleted."), "ok");
      if (editing?.id === r.id) close();
    }
  }

  const heading = (
    <div>
      <h3 className="flex items-center gap-2 text-lg"><Bot size={16} className="text-accent" /> {t("Penyedia AI tambahan (Wanshah 6, 7, …)", "Extra AI providers (Wanshah 6, 7, …)")}</h3>
      <p className="mt-1 max-w-2xl text-[12px] text-muted">
        {t("Tambah kunci Anthropic (Claude), kunci KiosAPI kedua atau mana-mana gerbang serasi OpenAI. Setiap satu menjadi robot yang boleh dipilih oleh penghala (paling pantas dan sihat, atau yang anda pin), disemak oleh pemeriksa API, dipin dari Telegram dan digunakan oleh Sembang AI untuk kerja yang anda tanda. Kunci dihantar hanya ke hos ia disimpan untuk; tukar endpoint tanpa kunci baharu dan kunci lama digugurkan. Kunci Gemini pergi ke kad Gemini.",
          "Add an Anthropic (Claude) key, a second KiosAPI key or any OpenAI-compatible gateway. Each becomes a robot the router may pick (fastest and healthy, or the one you pin), the API check probes, Telegram can pin and the AI chat can use, for the jobs you tick. A key is sent only to the host it was saved for; move the endpoint without a new key and the old key is dropped. A Gemini key goes on the Gemini card.")}
      </p>
    </div>
  );

  if (missing) {
    return (
      <Card className="space-y-2 p-4 text-sm text-muted" data-ai-providers>
        {heading}
        <p>{t("Jalankan supabase/074_ai_providers.sql sekali dahulu.", "Run supabase/074_ai_providers.sql once first.")}</p>
      </Card>
    );
  }

  const canAdd = rows.length < MAX_PROVIDERS;
  return (
    <Card className="space-y-4 p-4" data-ai-providers>
      {heading}
      {table.error && !missing && <p className="rounded-tile bg-danger/10 p-2 text-xs text-danger">{table.error}</p>}

      <ul className="space-y-2" data-ai-providers-list>
        {rows.map((r) => {
          const st = providerState(r, status[r.id], usageRows, now);
          const s = status[r.id];
          return (
            <li key={r.id} className="rounded-tile border border-line p-3 text-sm" data-ai-provider={r.id} data-state={st}>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${DOT_CLS[st]}`} aria-hidden="true" />
                <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] font-medium text-muted">{r.robot}</span>
                <span className="font-medium">{r.name}</span>
                <code className="rounded bg-surface-2 px-1 text-xs">{r.id}</code>
                <span className={`rounded-pill px-2 py-0.5 text-xs ${STATE_CLS[st]}`}>{w(STATE_WORDS[st])}</span>
                <span className="ml-auto flex items-center gap-2">
                  <Button size="sm" variant="ghost" onClick={() => startEdit(r)} aria-label={t("Sunting", "Edit")}><Pencil size={12} /> {t("Sunting", "Edit")}</Button>
                  <Button size="sm" variant={r.enabled === false ? "primary" : "ghost"} disabled={busy === `semasa_save_ai_provider${r.id}`} onClick={() => toggle(r)}>
                    <Power size={12} /> {r.enabled === false ? t("Hidupkan", "Switch on") : t("Matikan", "Switch off")}</Button>
                  <Button size="sm" variant="danger" onClick={() => remove(r)} disabled={busy === `semasa_delete_ai_provider${r.id}`}>
                    <Trash2 size={12} /> {sure === r.id ? t("Pasti? Klik lagi", "Sure? Click again") : t("Padam", "Delete")}</Button>
                </span>
              </div>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
                <dt className="text-muted">{t("Dialek", "Dialect")}</dt><dd>{r.dialect}</dd>
                <dt className="text-muted">{t("Hos", "Host")}</dt><dd className="truncate">{hostOf(r.base_url) || r.base_url}</dd>
                <dt className="text-muted">{t("Model", "Model")}</dt><dd className="truncate font-medium">{s?.model || r.model || t("Tiada", "None")}</dd>
                <dt className="text-muted">{t("Kunci", "Key")}</dt>
                <dd className="flex items-center gap-1"><KeyRound size={11} className="text-muted" />{r.key_hint ? <code>{r.key_hint}</code> : <span className="text-warn">{t("tiada: sunting dan tampal kunci", "none: edit and paste a key")}</span>}
                  {r.key_host && hostOf(r.base_url) !== String(r.key_host).toLowerCase() && <span className="text-warn"> · {t("terikat kepada", "bound to")} {r.key_host}</span>}</dd>
                <dt className="text-muted">{t("Kerja", "Jobs")}</dt>
                <dd className="flex flex-wrap gap-1">{JOB_CHOICES.filter(([k]) => (r.jobs || []).includes(k)).map(([k, words]) => (
                  <span key={k} className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px]" data-job={k}>{w(words).split(" (")[0]}</span>))}
                  {!(r.jobs || []).length && <span className="text-warn">{t("tiada kerja ditanda", "no job ticked")}</span>}</dd>
                {s && <><dt className="text-muted">{t("Semakan", "Check")}</dt>
                  <dd>{s.chat_ok ? `OK · ${fmtMs(s.chat_ms)}` : (s.error || t("gagal", "failed"))}{s.checked_at ? ` · ${timeAgo(s.checked_at)}` : ""}{s.models?.length ? ` · ${s.models.length} ${t("model", "models")}` : ""}</dd></>}
                {r.notes && <><dt className="text-muted">{t("Nota", "Notes")}</dt><dd className="break-words">{r.notes}</dd></>}
              </dl>
            </li>
          );
        })}
        {table.loading && !rows.length && <li className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> {t("Memuatkan…", "Loading…")}</li>}
        {!table.loading && !rows.length && <li className="text-xs text-muted" data-ai-providers-empty>{t("Belum ada penyedia tambahan. Lima robot sedia ada terus bekerja.", "No extra providers yet. The five built-in robots keep working.")}</li>}
      </ul>

      {!open && (
        <Button size="sm" onClick={startNew} disabled={!canAdd} data-ai-providers-add><Plus size={13} /> {t("Tambah penyedia", "Add a provider")}</Button>
      )}

      {open && (
        <form className="space-y-3 rounded-tile border border-dashed border-line p-3" data-ai-providers-form onSubmit={(e) => { e.preventDefault(); saveForm(); }}>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">{editing ? t(`Sunting ${editing.name}`, `Edit ${editing.name}`) : t("Penyedia baharu", "New provider")}</p>
            <Button type="button" size="sm" variant="ghost" onClick={close} aria-label={t("Tutup", "Close")}><X size={13} /></Button>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block"><Label>{t("Nama", "Name")}</Label>
              <Input value={form.name} maxLength={60} placeholder={t("Cth: Claude", "E.g. Claude")}
                onChange={(e) => setForm({ ...form, name: e.target.value, id: editing || form.idTouched ? form.id : slugOf(e.target.value) })} /></label>
            <label className="block"><Label hint={t("slug robot: huruf kecil, digit, sengkang", "the robot's slug: small letters, digits, dashes")}>ID</Label>
              <Input value={form.id} maxLength={24} disabled={!!editing} className="font-mono" placeholder="claude"
                onChange={(e) => setForm({ ...form, id: e.target.value.toLowerCase(), idTouched: true })} /></label>
            <label className="block"><Label>{t("Dialek", "Dialect")}</Label>
              <Select value={form.dialect} onChange={(v) => setForm({ ...form, dialect: v })} options={DIALECTS.map(([k, words]) => [k, w(words)])} className="w-full" data-ai-providers-dialect /></label>
            <label className="block"><Label hint={form.dialect === "anthropic" ? "https://api.anthropic.com" : "https://…/v1"}>{t("Endpoint", "Endpoint")}</Label>
              <Input value={form.base_url} placeholder={form.dialect === "anthropic" ? "https://api.anthropic.com" : "https://kiosapi.com/v1"} className="font-mono"
                onChange={(e) => setForm({ ...form, base_url: e.target.value })} /></label>
            <label className="block"><Label hint={t("model lalai; penghala boleh mencari yang lain", "the default model; the router may search others")}>{t("Model", "Model")}</Label>
              <Input value={form.model} placeholder={form.dialect === "anthropic" ? "claude-sonnet-4-5" : "gpt-5.6-sol"} className="font-mono"
                onChange={(e) => setForm({ ...form, model: e.target.value })} /></label>
            <label className="block"><Label hint={editing ? t("kosong = kekalkan kunci yang disimpan", "empty = keep the saved key") : t("hanya disimpan, tidak boleh dibaca semula", "stored only, never readable again")}>{t("Kunci API", "API key")}</Label>
              <span className="flex gap-1">
                <Input type={show ? "text" : "password"} value={form.api_key} autoComplete="off" spellCheck={false} className="font-mono" aria-label="API key"
                  placeholder={editing?.key_hint ? `${t("disimpan", "saved")} ${editing.key_hint}` : "sk-…"} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
                <Button type="button" size="sm" variant="ghost" onClick={() => setShow(!show)} aria-label={show ? t("Sembunyi", "Hide") : t("Tunjuk", "Show")}>{show ? <EyeOff size={13} /> : <Eye size={13} />}</Button>
              </span></label>
          </div>
          <fieldset className="space-y-1">
            <legend className="text-xs text-muted">{t("Boleh digunakan untuk:", "May be used for:")}</legend>
            {JOB_CHOICES.map(([job, words]) => (
              <label key={job} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.jobs.includes(job)} onChange={(e) => setForm({ ...form, jobs: toggleJob(form.jobs, job, e.target.checked) })} data-ai-providers-job={job} /> {w(words)}
              </label>
            ))}
          </fieldset>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> {t("Dihidupkan", "Switched on")}</label>
          <label className="block"><Label hint={t("pilihan", "optional")}>{t("Nota", "Notes")}</Label>
            <TextArea rows={2} value={form.notes} maxLength={400} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
          {keyWillDrop(form, editing) && (
            <p className="flex items-start gap-2 rounded-tile bg-warn/10 p-2 text-xs text-warn" data-ai-providers-drop>
              <AlertTriangle size={14} className="mt-px shrink-0" />
              {t(`Endpoint berpindah dari ${editing.key_host}: kunci yang disimpan akan digugurkan kecuali anda tampal kunci untuk hos baharu.`,
                `The endpoint moves off ${editing.key_host}: the saved key will be dropped unless you paste a key for the new host.`)}
            </p>
          )}
          {msg && (
            <p role="status" data-ai-providers-msg={msg.kind}
              className={`flex items-start gap-2 rounded-tile p-2 text-xs ${msg.kind === "err" ? "bg-danger/10 text-danger" : msg.kind === "ok" ? "bg-ok/10 text-ok" : "bg-surface-2 text-muted"}`}>
              {msg.kind === "err" ? <AlertTriangle size={14} className="mt-px shrink-0" /> : msg.kind === "ok" ? <CheckCircle2 size={14} className="mt-px shrink-0" /> : <Loader2 size={14} className="mt-px shrink-0 animate-spin" />}
              <span className="break-words">{msg.text}</span>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" size="sm" disabled={busy.startsWith("semasa_save_ai_provider")} data-ai-providers-save>
              {busy.startsWith("semasa_save_ai_provider") ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {t("Simpan", "Save")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={close}>{t("Batal", "Cancel")}</Button>
            <span className="text-[11.5px] text-muted">{t("Kunci dihantar hanya ke hos endpoint ini. Dialek anthropic bercakap /v1/messages dengan x-api-key; openai bercakap /chat/completions dengan Bearer.",
              "The key is sent only to this endpoint's host. The anthropic dialect speaks /v1/messages with x-api-key; openai speaks /chat/completions with Bearer.")}</span>
          </div>
        </form>
      )}
      {msg && !open && (
        <p role="status" data-ai-providers-msg={msg.kind} className={`flex items-start gap-2 rounded-tile p-2 text-xs ${msg.kind === "err" ? "bg-danger/10 text-danger" : msg.kind === "ok" ? "bg-ok/10 text-ok" : "bg-surface-2 text-muted"}`}>
          {msg.kind === "err" ? <AlertTriangle size={14} className="mt-px shrink-0" /> : <CheckCircle2 size={14} className="mt-px shrink-0" />}<span className="break-words">{msg.text}</span>
        </p>
      )}
    </Card>
  );
}

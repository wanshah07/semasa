import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound, Loader2, Plus, Power, Save, Sparkles, Trash2 } from "lucide-react";
import { errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import {
  JOB_CHOICES, MAX_KEYS, STATE_CLS, STATE_WORDS, keyState, restMinutes, settingsOf, toggleJob, usableCount, validKey,
} from "../lib/geminiKeys";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Label } from "./ui/Field";

/* Gemini with several API keys, picked automatically (Wan, 6 Nov 2026: "add gemini api key I can add multiple and its auto select
   same like chatgpt"). Any number of Google AI Studio keys (supabase/061, which this page can never read back); Semasa picks the
   least recently used one that is not refused or resting, for Motion's scene pictures (after ChatGPT) and as the AI team's fourth
   robot for the jobs ticked below. The page shows a hint, a status and the last error, never a key. */

export default function GeminiKeys({ settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const [rows, setRows] = useState(null);         // null while loading
  const [missing, setMissing] = useState(false);  // 061 not run
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState("");
  const [form, setForm] = useState(settingsOf(settings?.gemini));
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    const { data, error } = await supabase.rpc("semasa_gemini_keys_list");
    if (error) {
      if (/semasa_gemini_keys_list|PGRST202|42883|does not exist/i.test(`${error.code} ${error.message}`)) setMissing(true);
      else onToast?.(errText(error), "danger");
      return;
    }
    setMissing(false);
    setRows(Array.isArray(data) ? data : []);
    setNow(Date.now());
  }, [onToast]);

  useEffect(() => { load(); const id = setInterval(load, 60_000); return () => clearInterval(id); }, [load]);
  const saved = JSON.stringify(settingsOf(settings?.gemini));
  useEffect(() => { setForm(JSON.parse(saved)); }, [saved]);

  async function rpc(name, args, done) {
    setBusy(name + (args.p_id || ""));
    const { data, error } = await supabase.rpc(name, args);
    setBusy("");
    if (error) { onToast?.(errText(error), "danger"); return false; }
    setRows(Array.isArray(data) ? data : rows);
    if (done) onToast?.(done, "ok");
    return true;
  }

  async function add() {
    if (!validKey(key)) return onToast?.(t("Itu tidak kelihatan seperti kunci Google AI Studio (20 hingga 120 huruf, nombor, - dan _, tanpa ruang).", "That does not look like a Google AI Studio key (20 to 120 letters, digits, - and _, no spaces)."), "warn");
    if (await rpc("semasa_gemini_key_add", { p_label: label.trim(), p_key: key.trim() },
      t("Kunci ditambah. Ia diuji pada panggilan pertama.", "Key added. It is tried on its first call."))) { setKey(""); setLabel(""); setShow(false); }
  }

  async function remove(r) {
    if (sure !== r.id) { setSure(r.id); setTimeout(() => setSure(""), 6000); return; }
    setSure("");
    await rpc("semasa_gemini_key_delete", { p_id: r.id }, t("Kunci dipadam.", "Key deleted."));
  }

  async function saveSettings(next) {
    try { await save("gemini", next); onToast?.(t("Disimpan. Larian seterusnya menggunakannya.", "Saved. The next run uses it."), "ok"); } catch (e) {
      onToast?.(/0 rows/.test(e.message) ? t("Jalankan supabase/061_gemini_keys.sql dahulu.", "Run supabase/061_gemini_keys.sql first.") : e.message, "danger");
    }
  }

  if (missing) {
    return (
      <Card className="p-4 text-sm text-muted" data-gemini>
        <h3 className="flex items-center gap-2 text-lg text-ink"><Sparkles size={16} /> {t("Kunci Gemini", "Gemini keys")}</h3>
        <p className="mt-1">{t("Jalankan supabase/061_gemini_keys.sql sekali dahulu.", "Run supabase/061_gemini_keys.sql once first.")}</p>
      </Card>
    );
  }

  const usable = usableCount(rows, now);
  return (
    <Card className="space-y-4 p-4" data-gemini>
      <div>
        <h3 className="flex items-center gap-2 text-lg"><Sparkles size={16} className="text-accent" /> {t("Kunci Gemini (Wanshah 4)", "Gemini keys (Wanshah 4)")}</h3>
        <p className="mt-1 max-w-2xl text-[12px] text-muted">
          {t("Tambah beberapa kunci Google AI Studio. Semasa memilih sendiri satu yang paling lama tidak digunakan dan tidak ditolak atau sedang berehat; kunci yang kena had kadar berehat 30 minit, kunci yang ditolak Google dilangkau sehingga anda hidupkannya semula. Gemini melukis gambar babak Motion selepas ChatGPT dan menjadi robot keempat pasukan AI untuk kerja yang anda tanda.",
            "Add several Google AI Studio keys. Semasa picks one itself: the one used least recently that is not refused or resting. A key that hits a rate limit rests 30 minutes, and a key Google refuses is skipped until you switch it on again. Gemini draws Motion's scene pictures after ChatGPT and is the AI team's fourth robot for the jobs you tick.")}
        </p>
      </div>

      <ul className="space-y-2">
        {(rows || []).map((r) => {
          const st = keyState(r, now);
          return (
            <li key={r.id} className="rounded-tile border border-line p-3 text-sm" data-gemini-key={r.id} data-state={st}>
              <div className="flex flex-wrap items-center gap-2">
                <KeyRound size={14} className="text-muted" />
                <span className="font-medium">{r.label || t("Tanpa nama", "Unnamed")}</span>
                <code className="rounded bg-surface-2 px-1 text-xs">{r.hint}</code>
                <span className={`rounded-pill px-2 py-0.5 text-xs ${STATE_CLS[st]}`}>{STATE_WORDS[st][L]}{st === "resting" ? ` · ${restMinutes(r, now)} min` : ""}</span>
                <span className="text-xs text-muted">{r.last_ok_at ? `${t("berjaya", "worked")} ${timeAgo(r.last_ok_at)}` : t("belum berjaya", "not worked yet")} · {r.calls} {t("panggilan", "calls")}</span>
                <span className="ml-auto flex items-center gap-2">
                  <Button size="sm" variant={r.enabled ? "ghost" : "primary"} disabled={busy === `semasa_gemini_key_set${r.id}`}
                    onClick={() => rpc("semasa_gemini_key_set", { p_id: r.id, p_enabled: !r.enabled })}><Power size={12} /> {r.enabled ? t("Matikan", "Switch off") : t("Hidupkan", "Switch on")}</Button>
                  <Button size="sm" variant="danger" onClick={() => remove(r)} disabled={busy === `semasa_gemini_key_delete${r.id}`}><Trash2 size={12} /> {sure === r.id ? t("Pasti? Klik lagi", "Sure? Click again") : t("Padam", "Delete")}</Button>
                </span>
              </div>
              {r.last_error && st !== "ok" && <p className="mt-1 break-words text-xs text-danger" data-gemini-error>{r.last_error}</p>}
            </li>
          );
        })}
        {rows === null && <li className="flex items-center gap-2 text-xs text-muted"><Loader2 size={13} className="animate-spin" /> {t("Memuatkan…", "Loading…")}</li>}
        {rows && !rows.length && <li className="text-xs text-muted" data-gemini-empty>{t("Belum ada kunci. Tambah satu di bawah.", "No keys yet. Add one below.")}</li>}
      </ul>
      {rows?.length > 0 && <p className="text-xs text-muted" data-gemini-count>{usable} {t("daripada", "of")} {rows.length} {t("kunci boleh digunakan sekarang.", "keys can be used now.")}</p>}

      <div className="space-y-2 rounded-tile border border-dashed border-line p-3" data-gemini-add>
        <p className="text-sm font-medium">{t("Tambah kunci", "Add a key")}</p>
        <div className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]">
          <label className="block"><Label hint={t("pilihan", "optional")}>{t("Nama", "Name")}</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} placeholder={t("Cth: Akaun 1", "E.g. Account 1")} /></label>
          <label className="block"><Label hint={t("hanya disimpan, tidak boleh dibaca semula", "stored only, never readable again")}>{t("Kunci API", "API key")}</Label>
            <span className="flex gap-1">
              <Input type={show ? "text" : "password"} value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" spellCheck={false}
                placeholder="AIza…" aria-label="API key" className="font-mono" />
              <Button type="button" size="sm" variant="ghost" onClick={() => setShow(!show)} aria-label={show ? t("Sembunyi", "Hide") : t("Tunjuk", "Show")}>{show ? <EyeOff size={13} /> : <Eye size={13} />}</Button>
            </span></label>
          <div className="flex items-end"><Button size="sm" onClick={add} disabled={busy === "semasa_gemini_key_add" || !key.trim() || (rows?.length || 0) >= MAX_KEYS}>
            {busy === "semasa_gemini_key_add" ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} {t("Tambah", "Add")}</Button></div>
        </div>
        <p className="text-[11.5px] text-muted">{t(`Sehingga ${MAX_KEYS} kunci. Kunci percuma mungkin membenarkan Google menggunakan apa yang dihantar untuk memperbaik produknya: kerana itu Gemini hanya digunakan untuk kerja yang anda tanda di bawah.`,
          `Up to ${MAX_KEYS} keys. A free key may let Google use what is sent to improve its products, which is why Gemini only does the jobs you tick below.`)}</p>
      </div>

      <div className="space-y-3 rounded-tile border border-line p-3" data-gemini-settings>
        <p className="text-sm font-medium">{t("Apa yang Gemini buat", "What Gemini does")}</p>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> {t("Gemini dihidupkan", "Gemini is on")}</label>
        <fieldset className="space-y-1">
          <legend className="text-xs text-muted">{t("Boleh menjadi robot penulis teks untuk:", "May be the text/vision robot for:")}</legend>
          {JOB_CHOICES.map(([job, words]) => (
            <label key={job} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.jobs.includes(job)} onChange={(e) => setForm({ ...form, jobs: toggleJob(form.jobs, job, e.target.checked) })} data-gemini-job={job} /> {words[L]}
            </label>
          ))}
          {form.jobs.includes("reader") && <p className="text-xs text-warn" data-gemini-warn>{t("Ini menghantar nota Otak AI, resit, bil dan CRM kepada Google. Gunakan kunci berbayar sahaja.", "This sends Otak AI notes, receipts, billing and CRM text to Google. Use paid-tier keys only.")}</p>}
        </fieldset>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.images} onChange={(e) => setForm({ ...form, images: e.target.checked })} /> {t("Lukis gambar babak Motion (selepas ChatGPT)", "Draw Motion scene pictures (after ChatGPT)")}</label>
        <div className="flex flex-wrap items-end gap-3">
          <label className="block"><Label>{t("Model teks", "Text model")}</Label><Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} className="w-52" aria-label="Text model" /></label>
          <label className="block"><Label>{t("Model gambar", "Image model")}</Label><Input value={form.image_model} onChange={(e) => setForm({ ...form, image_model: e.target.value })} className="w-60" aria-label="Image model" /></label>
          <label className="block"><Label>{t("Gambar paling banyak (tanpa ChatGPT)", "Most pictures (without ChatGPT)")}</Label>
            <select value={form.max_images} onChange={(e) => setForm({ ...form, max_images: Number(e.target.value) })} className="rounded-pill border border-line bg-surface px-3 py-2 text-xs" aria-label="Most pictures">
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
          <Button size="sm" onClick={() => saveSettings(form)} data-gemini-save><Save size={13} /> {t("Simpan", "Save")}</Button>
        </div>
        <p className="text-[11.5px] text-muted">{t("Jika model tidak wujud, pasukan AI mencari model yang menjawab daripada senarai kunci itu sendiri; lukisan gambar mencari model gambar.", "If a model does not exist, the AI team searches the key's own list for one that answers; the picture call looks for an image model.")}</p>
      </div>
    </Card>
  );
}

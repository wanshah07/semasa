import { useCallback, useEffect, useMemo, useState } from "react";
import { Clipboard, KeyRound, Loader2, Trash2, UploadCloud } from "lucide-react";
import { IMPORT_COLUMNS, TOKEN_COLUMNS, curlExample, endpointUrl, importStatus, tokenRows } from "../lib/videoImport";
import { stampMYT, timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { errText, supabase } from "../lib/SupabaseClient";
import Button from "./ui/Button";
import { Input, Label } from "./ui/Field";

/* Import video (Wan, 17 Nov 2026): an MP4 made outside Semasa (Nous Hermes, Nexabot, huashu-motion) is sent to one address with a key
   made here, checked by the worker, and becomes a DRAFT post on the next free slot. Nothing is approved by it: the post waits for
   your own Approve, here or on Telegram. A key is shown ONCE; only its hash is kept (supabase/087_video_import.sql). */

const TONE = { ok: "text-ok", danger: "text-danger", muted: "text-muted" };

export default function VideoImportCard({ onToast, go }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const base = import.meta.env.VITE_SUPABASE_URL || "";
  const [tokens, setTokens] = useState([]);
  const [imports, setImports] = useState([]);
  const [label, setLabel] = useState("");
  const [fresh, setFresh] = useState("");                 // the key just made: shown once, held only in this state
  const [busy, setBusy] = useState("");
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!supabase) return;
    const [k, i] = await Promise.all([
      supabase.from("semasa_import_tokens").select(TOKEN_COLUMNS).order("created_at", { ascending: false }).limit(30),
      supabase.from("semasa_video_imports").select(IMPORT_COLUMNS).order("created_at", { ascending: false }).limit(15),
    ]);
    const bad = k.error || i.error;
    if (bad) { setMissing(/semasa_import_tokens|semasa_video_imports|schema cache|does not exist/i.test(errText(bad))); setError(errText(bad)); return; }
    setMissing(false); setError(""); setTokens(k.data || []); setImports(i.data || []);
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(() => { if (!document.hidden) load(); }, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const rows = useMemo(() => tokenRows(tokens), [tokens]);
  const endpoint = endpointUrl(base);

  async function make(e) {
    e.preventDefault();
    if (!label.trim()) return;
    setBusy("make");
    const { data, error: err } = await supabase.rpc("semasa_import_token_create", { p_label: label.trim() });
    setBusy("");
    if (err) return onToast(/function|schema cache/i.test(err.message || "") ? t("Jalankan supabase/087_video_import.sql dahulu.", "Run supabase/087_video_import.sql first.") : errText(err), "danger");
    setFresh(String(data || "")); setLabel(""); load();
  }
  async function revoke(row) {
    setBusy(row.id);
    const { error: err } = await supabase.rpc("semasa_import_token_revoke", { p_id: row.id });
    setBusy("");
    if (err) return onToast(errText(err), "danger");
    onToast(t(`Kunci "${row.label}" dihentikan.`, `The key "${row.label}" is revoked.`), "ok");
    load();
  }
  const copy = async (text, msg) => {
    try { await navigator.clipboard.writeText(text); onToast(msg, "ok"); } catch { onToast(t("Tidak dapat salin; salin dengan tangan.", "Could not copy; select and copy by hand."), "danger"); }
  };

  return (
    <details className="mt-6 rounded-card border border-line/80 bg-surface p-4" data-video-import>
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold"><UploadCloud size={14} /> {t("Import video dari luar", "Import a video from outside")}
        <span className="font-normal text-muted">{t("(Hermes, Nexabot, huashu-motion)", "(Hermes, Nexabot, huashu-motion)")}</span></summary>
      <p className="mt-2 max-w-3xl text-[12px] text-muted">{t(
        "Ejen luar menghantar MP4 siap ke satu alamat dengan kunci yang anda buat di sini. Semasa menyemak fail dan kapsyen (peraturan yang sama seperti post lain), kemudian membuat DRAF post di slot kosong seterusnya. Tiada apa-apa diluluskan atau disiarkan oleh import: post menunggu Lulus anda, di sini atau di Telegram.",
        "An outside agent sends a finished MP4 to one address with a key you make here. Semasa checks the file and the caption (the same rules as any post), then makes a DRAFT post on the next free slot. An import approves and posts nothing: the post waits for your own Approve, here or on Telegram.")}</p>
      {missing && <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px] text-warn" data-import-needs-sql>{t("Jalankan supabase/087_video_import.sql sekali dalam Supabase, kemudian muat semula.", "Run supabase/087_video_import.sql once in Supabase, then reload.")}</p>}
      {!missing && error && <p className="mt-2 text-[12px] text-warn">{error}</p>}

      <div className="mt-3 text-[12px]">
        <Label>{t("Alamat untuk ejen", "The address for the agent")}</Label>
        <div className="flex flex-wrap items-center gap-2">
          <code className="break-all rounded-tile bg-surface-2 px-2 py-1" data-import-endpoint>{endpoint}</code>
          <Button type="button" size="sm" variant="ghost" onClick={() => copy(endpoint, t("Alamat disalin.", "Address copied."))} aria-label={t("Salin alamat", "Copy the address")}><Clipboard size={12} /></Button>
        </div>
        <p className="mt-1 text-muted">{t("Fail sehingga 50 MB (multipart atau badan mentah), 15 MiB dalam JSON, atau pautan https awam. Panjang sehingga 90 s.", "Files up to 50 MB (multipart or a raw body), 15 MiB inside JSON, or a public https link. Up to 90 s long.")}</p>
      </div>

      <form onSubmit={make} className="mt-4 flex flex-wrap items-end gap-2">
        <label className="min-w-[14rem] flex-1">
          <Label>{t("Nama kunci baharu", "New key name")}</Label>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={60} placeholder="hermes" data-import-label />
        </label>
        <Button type="submit" size="sm" disabled={busy === "make" || !label.trim() || missing} data-import-make>
          {busy === "make" ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />} {t("Buat kunci", "Make a key")}</Button>
      </form>

      {fresh && (
        <div className="mt-3 rounded-tile border border-warn/60 bg-warn/5 p-3 text-[12px]" data-import-fresh>
          <p className="font-semibold">{t("Salin kunci ini sekarang. Ia tidak akan ditunjukkan lagi.", "Copy this key now. It will not be shown again.")}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <code className="break-all rounded-tile bg-surface-2 px-2 py-1" data-import-token>{fresh}</code>
            <Button type="button" size="sm" variant="soft" onClick={() => copy(fresh, t("Kunci disalin.", "Key copied."))}><Clipboard size={12} /> {t("Salin", "Copy")}</Button>
          </div>
          <pre className="mt-2 overflow-x-auto rounded-tile bg-surface-2 p-2 text-[11px]" data-import-curl>{curlExample(base, fresh)}</pre>
          <div className="mt-1 flex gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => copy(curlExample(base, fresh), t("Contoh curl disalin.", "curl example copied."))}><Clipboard size={12} /> {t("Salin contoh curl", "Copy the curl example")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setFresh("")} data-import-done>{t("Saya sudah salin", "I have copied it")}</Button>
          </div>
        </div>
      )}

      <div className="mt-4">
        <p className="text-[13px] font-semibold">{t("Kunci", "Keys")}</p>
        {rows.length === 0 ? <p className="mt-1 text-[12px] text-muted">{t("Belum ada kunci.", "No keys yet.")}</p> : (
          <ul className="mt-1 divide-y divide-line/60 text-[12px]" data-import-tokens>
            {rows.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                <span className={r.active ? "" : "text-muted line-through"}><b>{r.label}</b> · {t("dibuat", "made")} {stampMYT(r.created_at)} · {r.last_used_at ? `${t("dipakai", "used")} ${timeAgo(r.last_used_at)}` : t("belum dipakai", "never used")}
                  {!r.active && ` · ${t("dihentikan", "revoked")}`}</span>
                {r.active && <Button type="button" size="sm" variant="ghost" disabled={busy === r.id} onClick={() => revoke(r)} aria-label={t("Hentikan kunci", "Revoke the key")}><Trash2 size={12} /> {t("Hentikan", "Revoke")}</Button>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4">
        <p className="text-[13px] font-semibold">{t("Import terkini", "Latest imports")}</p>
        {imports.length === 0 ? <p className="mt-1 text-[12px] text-muted">{t("Belum ada video diterima.", "No video received yet.")}</p> : (
          <ul className="mt-1 divide-y divide-line/60 text-[12px]" data-import-list>
            {imports.map((r) => {
              const s = importStatus(r);
              return (
                <li key={r.id} className="py-1.5">
                  <span className="text-muted">{stampMYT(r.created_at)} · {r.source || r.token_label || "-"}</span>
                  <span className={`ml-2 ${TONE[s.tone]} [overflow-wrap:anywhere]`}>{s.words[L]}</span>
                  {r.status === "done" && r.post_id && go && <button type="button" className="ml-2 text-accent underline" onClick={() => go("post")}>{t("Buka draf", "Open the draft")}</button>}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </details>
  );
}

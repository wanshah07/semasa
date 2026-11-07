import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ChevronDown, ChevronUp, ExternalLink, KeyRound, Layers, Loader2, Pencil, Plus, Save, Search, Trash2, X } from "lucide-react";
import pkg from "../../package.json";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useTable } from "../lib/hooks";
import { useLang } from "../lib/i18n";
import { KINDS, KIND_WORDS, SOURCE_WORDS, buildStack, countByKind, filterStack, itemRow } from "../lib/stack";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Input, Label, Select, TextArea } from "../components/ui/Field";

/* Senarai teknologi (Wan, 11 Oct 2026, Phase 4: "repo registration, repo library dengan URL, API library dan model dia, satu
   senarai semua API/SDK/CLI"). One list of every API (with its models), SDK, CLI, repo and service, read from the code, the probe
   and the repo tables (lib/stack.js), plus what Wan adds himself (semasa_tech_items, supabase/068). Repos are registered on Repo
   pejabat and pasted on Pustaka repo; this page links to both rather than keeping a second list. */
const LIVE_CLS = { up: "bg-ok", models: "bg-warn", down: "bg-danger", nokey: "bg-muted" };
const BLANK = { kind: "api", name: "", url: "", docs_url: "", models: "", env_key: "", used_for: "", status: "active", notes: "" };

export default function StackTab({ onToast, go }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const probeT = useTable(TABLES.apiStatus, { enabled: true, order: "role", ascending: true, limit: 50, realtime: false, everyMs: 300_000 });
  const reposT = useTable(TABLES.repos, { enabled: true, order: "full_name", ascending: true, limit: 200, realtime: false });
  const libT = useTable(TABLES.repoLibrary, { enabled: true, order: "created_at", limit: 500, realtime: false });
  const mineT = useTable(TABLES.techItems, { enabled: true, order: "name", ascending: true, limit: 500, realtime: false });
  const mineMissing = /tech_items|PGRST205|42P01|does not exist/i.test(mineT.error || "");
  const rows = useMemo(() => buildStack({ pkg, probe: probeT.rows, repos: reposT.rows, library: libT.rows, mine: mineMissing ? [] : mineT.rows }, L),
    [probeT.rows, reposT.rows, libT.rows, mineT.rows, mineMissing, L]);
  const counts = useMemo(() => countByKind(rows), [rows]);
  const [kind, setKind] = useState("all");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState("");
  const [form, setForm] = useState(null);          // null, or the item being added / edited
  const [busy, setBusy] = useState("");
  const [sure, setSure] = useState("");
  const shown = useMemo(() => filterStack(rows, kind, q), [rows, kind, q]);
  const migrate = t("Jalankan supabase/068_tech_items.sql sekali dahulu.", "Run supabase/068_tech_items.sql once first.");

  async function saveItem() {
    const { row, error } = itemRow(form, t);
    if (error) return onToast(error, "warn");
    setBusy("save");
    const q2 = form.id ? supabase.from(TABLES.techItems).update(row).eq("id", form.id) : supabase.from(TABLES.techItems).insert(row);
    const { error: e } = await q2;
    setBusy("");
    if (e) {
      const msg = errText(e);
      return onToast(/tech_items|PGRST205|42P01/.test(msg) ? migrate : /duplicate|23505/.test(msg) ? t("Nama itu sudah ada untuk jenis ini.", "That name already exists for this kind.") : msg, "danger");
    }
    setForm(null);
    mineT.reload?.();
    onToast(form.id ? t("Dikemas kini.", "Updated.") : t("Ditambah ke senarai.", "Added to the list."), "ok");
  }

  async function remove(r) {
    if (sure !== r.id) { setSure(r.id); setTimeout(() => setSure(""), 6000); return; }
    setBusy(`del-${r.id}`); setSure("");
    const { error } = await supabase.from(TABLES.techItems).delete().eq("id", r.id);
    setBusy("");
    if (error) return onToast(errText(error), "danger");
    mineT.reload?.();
    onToast(t("Dibuang daripada senarai.", "Removed from the list."), "ok");
  }

  const edit = (r) => {
    const m = (mineT.rows || []).find((x) => x.id === r.id);
    if (m) setForm({ ...BLANK, ...m, models: (m.models || []).join("\n") });
  };
  const chips = [["all", t("Semua", "All")], ...KINDS.map((k) => [k, KIND_WORDS[k][L]])];

  return (
    <main className="mx-auto max-w-page space-y-6 px-4 pb-20 pt-10 sm:px-6" data-stack-page>
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Senarai teknologi", "Technology list")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Satu senarai setiap API (dengan modelnya), SDK, CLI, repo dan servis yang Semasa guna. Kebanyakannya dibaca terus daripada kod, aliran kerja dan pemeriksa API; tambah sendiri apa yang belum ada.",
            "One list of every API (with its models), SDK, CLI, repo and service Semasa uses. Most of it is read straight from the code, the workflows and the API probe; add yourself what is not there yet.")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => go?.("office")} data-stack-go="office">{t("Daftar repo", "Register repos")}</Button>
          <Button size="sm" variant="ghost" onClick={() => go?.("repo")} data-stack-go="repo">{t("Pustaka repo", "Repo library")}</Button>
          <Button size="sm" variant="ghost" onClick={() => go?.("api")} data-stack-go="api">{t("Status API", "API status")}</Button>
          <Button size="sm" onClick={() => setForm({ ...BLANK })} disabled={mineMissing} data-stack-add><Plus size={13} /> {t("Tambah", "Add")}</Button>
        </div>
      </motion.div>

      {mineMissing && <p className="rounded-tile bg-warn/10 p-3 text-sm text-warn">{migrate} {t("Senarai daripada kod tetap dipaparkan.", "The list from the code still shows.")}</p>}

      {form && (
        <Card className="space-y-3 p-5" data-stack-form>
          <div className="flex items-center justify-between"><p className="font-medium">{form.id ? t("Ubah", "Edit") : t("Tambah ke senarai", "Add to the list")}</p>
            <button type="button" onClick={() => setForm(null)} aria-label={t("Tutup", "Close")} className="text-muted hover:text-ink"><X size={16} /></button></div>
          <div className="grid gap-3 sm:grid-cols-2 [&>*]:min-w-0">
            <label className="block"><Label>{t("Jenis", "Kind")}</Label>
              <Select value={form.kind} onChange={(v) => setForm({ ...form, kind: v })} options={[["api", "API"], ["sdk", "SDK"], ["cli", "CLI"], ["service", t("Servis", "Service")]]} className="w-full" /></label>
            <label className="block"><Label>{t("Nama", "Name")}</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} data-stack-name /></label>
            <label className="block"><Label hint="https://">{t("Alamat", "Address")}</Label><Input value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} data-stack-url /></label>
            <label className="block"><Label hint="https://">{t("Dokumentasi", "Docs")}</Label><Input value={form.docs_url} onChange={(e) => setForm({ ...form, docs_url: e.target.value })} /></label>
            <label className="block"><Label hint={t("nama sahaja, cth OPENAI_API_KEY; jangan tampal kunci", "the name only, e.g. OPENAI_API_KEY; never paste the key")}>{t("Nama rahsia", "Secret name")}</Label>
              <Input value={form.env_key} onChange={(e) => setForm({ ...form, env_key: e.target.value })} spellCheck={false} className="font-mono" data-stack-env /></label>
            <label className="block"><Label>Status</Label>
              <Select value={form.status} onChange={(v) => setForm({ ...form, status: v })} options={[["active", t("Aktif", "Active")], ["trial", t("Percubaan", "Trial")], ["retired", t("Bersara", "Retired")]]} className="w-full" /></label>
          </div>
          <label className="block"><Label hint={t("satu setiap baris, atau dipisah koma", "one a line, or comma-separated")}>{t("Model", "Models")}</Label>
            <TextArea rows={3} value={form.models} onChange={(e) => setForm({ ...form, models: e.target.value })} spellCheck={false} className="font-mono text-xs" data-stack-models /></label>
          <label className="block"><Label>{t("Untuk apa", "Used for")}</Label><Input value={form.used_for} onChange={(e) => setForm({ ...form, used_for: e.target.value })} maxLength={300} /></label>
          <label className="block"><Label hint={t("pilihan", "optional")}>{t("Nota", "Notes")}</Label><TextArea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} maxLength={1000} /></label>
          <Button size="sm" onClick={saveItem} disabled={busy === "save"} data-stack-save>{busy === "save" ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {t("Simpan", "Save")}</Button>
        </Card>
      )}

      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" className="flex flex-wrap gap-1.5" data-stack-kinds>
            {chips.map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => setKind(k)} data-kind={k}
                className={`rounded-pill px-3 py-1 text-xs font-medium ${kind === k ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>{label} <span className="tabular-nums opacity-70">{counts[k] ?? 0}</span></button>
            ))}
          </div>
          <label className="relative ml-auto w-full sm:w-72">
            <Search size={13} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari nama, model, rahsia…", "Search name, model, secret…")} className="w-full pl-8" data-stack-search />
          </label>
        </div>

        <ul className="divide-y divide-line" data-stack-list>
          {shown.map((r) => {
            const isOpen = open === r.key;
            const more = r.models.length > 0 || r.env.length > 0 || r.store || r.docs || r.notes;
            return (
              <li key={r.key} className="py-2.5" data-stack-row={r.key} data-kind={r.kind}>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="w-14 shrink-0 rounded-pill bg-surface-2 px-2 py-0.5 text-center text-[11px] font-semibold uppercase text-muted">{KIND_WORDS[r.kind]?.[L] || r.kind}</span>
                  {r.live && <span className={`h-2 w-2 shrink-0 rounded-full ${LIVE_CLS[r.live] || "bg-muted"}`} title={r.live} />}
                  {r.url ? <a href={r.url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1 font-medium hover:underline"><span className="[overflow-wrap:anywhere]">{r.name}</span><ExternalLink size={11} className="shrink-0 text-muted" /></a>
                    : <span className="min-w-0 font-medium [overflow-wrap:anywhere]">{r.name}</span>}
                  {r.version && <span className="font-mono text-[11px] text-muted">{r.version}</span>}
                  {r.models.length > 0 && <span className="rounded-pill bg-accent/10 px-2 py-0.5 text-[11px] text-accent" data-stack-models-count>{t(`${r.models.length} model`, `${r.models.length} model${r.models.length === 1 ? "" : "s"}`)}</span>}
                  {r.status !== "active" && <span className="rounded-pill bg-warn/15 px-2 py-0.5 text-[11px] text-warn">{r.status === "trial" ? t("percubaan", "trial") : t("bersara", "retired")}</span>}
                  <span className="rounded-pill border border-line px-2 py-0.5 text-[11px] text-muted">{SOURCE_WORDS[r.source]?.[L] || r.source}</span>
                  <span className="ml-auto flex items-center gap-1">
                    {r.source === "mine" && <>
                      <Button size="sm" variant="ghost" onClick={() => edit(r)} aria-label={t("Ubah", "Edit")}><Pencil size={12} /></Button>
                      <Button size="sm" variant="danger" onClick={() => remove(r)} disabled={busy === `del-${r.id}`}><Trash2 size={12} /> {sure === r.id ? t("Pasti?", "Sure?") : ""}</Button>
                    </>}
                    {more && <Button size="sm" variant="ghost" onClick={() => setOpen(isOpen ? "" : r.key)} aria-label={t("Butiran", "Details")} data-stack-open>{isOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}</Button>}
                  </span>
                </div>
                {r.used && <p className="mt-0.5 pl-16 text-xs text-muted [overflow-wrap:anywhere]">{r.used}</p>}
                {isOpen && (
                  <div className="mt-2 space-y-2 pl-16 text-xs" data-stack-detail>
                    {(r.env.length > 0 || r.store) && (
                      <p className="flex flex-wrap items-center gap-1.5"><KeyRound size={12} className="text-muted" />
                        {r.env.map((e) => <code key={e} className="rounded bg-surface-2 px-1.5 py-0.5">{e}</code>)}
                        {r.store && <span className="text-muted">{t(`kunci dalam jadual ${r.store}`, `key in the ${r.store} table`)}</span>}</p>
                    )}
                    {r.docs && <a href={r.docs} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">{t("Dokumentasi", "Docs")} <ExternalLink size={11} /></a>}
                    {r.notes && <p className="text-muted">{r.notes}</p>}
                    {r.models.length > 0 && (
                      <div className="flex flex-wrap gap-1" data-stack-model-list>
                        {r.models.map((m, i) => <span key={m} className={`rounded-pill px-2 py-0.5 text-[11px] ${i === 0 && r.source !== "mine" ? "bg-accent/15 text-accent" : "bg-surface-2"}`}>{m}</span>)}
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
          {!shown.length && <li className="py-6 text-center text-sm text-muted"><Layers size={16} className="mx-auto mb-1" />{t("Tiada yang sepadan.", "Nothing matches.")}</li>}
        </ul>
      </Card>
    </main>
  );
}

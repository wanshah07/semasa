import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Building2, Check, Pencil, Plus, Receipt, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { DEFAULT_BUSINESS, newBusinessBilling, slugOf } from "../lib/businesses";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label } from "../components/ui/Field";

/* Syarikat (Wan, 11 Oct 2026: "business separate to WS REGULAB and VALORITH, I able to add the business"). One row per
   business (supabase/066 semasa_businesses). A new business starts with its own name and prefixes, no bank and auto-send off;
   its letterhead, bank, terms and numbering are set in Billing → Settings while that business is picked. A business is never
   deleted (its papers keep their numbers); one no longer used is switched off and leaves the pickers. */
export default function BusinessesTab({ settings, onToast, go }) {
  const { t } = useLang();
  const bizT = useTable(TABLES.businesses, { enabled: true, order: "sort", ascending: true, limit: 100, realtime: false });
  const docsT = useTable(TABLES.billingDocs, { enabled: true, limit: 3000, realtime: false });
  const clientsT = useTable(TABLES.clients, { enabled: true, limit: 3000, realtime: false });
  const contactsT = useTable(TABLES.crmContacts, { enabled: true, limit: 3000, realtime: false });
  const [name, setName] = useState("");
  const [busy, setBusy] = useState("");
  const [renaming, setRenaming] = useState(null);        // { id, name }
  const missing = /semasa_businesses/.test(bizT.error || "");
  const rows = useMemo(() => [...bizT.rows].sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0)), [bizT.rows]);
  const count = (list, id) => list.filter((r) => (r.business_id || DEFAULT_BUSINESS) === id).length;

  async function run(key, fn, ok) {
    setBusy(key);
    try { await fn(); bizT.reload(); if (ok) onToast(ok, "ok"); }
    catch (e) { onToast(e.message || String(e), "danger"); }
    finally { setBusy(""); }
  }
  const add = () => run("add", async () => {
    const n = name.trim();
    if (!n) throw new Error(t("Tulis nama syarikat dahulu.", "Write the business's name first."));
    if (rows.some((b) => b.name.trim().toLowerCase() === n.toLowerCase())) throw new Error(t("Syarikat dengan nama itu sudah ada.", "A business with that name already exists."));
    const id = slugOf(n, rows.map((b) => b.id));
    const ws = rows.find((b) => b.id === DEFAULT_BUSINESS)?.billing || settings?.billing || {};
    const { error } = await supabase.from(TABLES.businesses).insert({ id, name: n, billing: newBusinessBilling(n, id, ws), sort: Math.max(0, ...rows.map((b) => b.sort ?? 0)) + 1 });
    if (error) throw new Error(errText(error));
    setName("");
  }, t("Syarikat ditambah. Lengkapkan letterhead, bank dan awalan nombor di Bil → Tetapan.", "Business added. Fill in its letterhead, bank and number prefixes in Billing → Settings."));
  const rename = () => run(`r-${renaming.id}`, async () => {
    const n = renaming.name.trim();
    if (!n) throw new Error(t("Nama tidak boleh kosong.", "The name cannot be empty."));
    const { error } = await supabase.from(TABLES.businesses).update({ name: n }).eq("id", renaming.id);
    if (error) throw new Error(errText(error));
    setRenaming(null);
  }, t("Nama dikemas kini.", "Name updated."));
  const toggle = (b) => run(`a-${b.id}`, async () => {
    if (b.id === DEFAULT_BUSINESS && b.active !== false) throw new Error(t("WS REGULAB ialah syarikat utama dan tidak boleh dimatikan.", "WS REGULAB is the main business and cannot be switched off."));
    const { error } = await supabase.from(TABLES.businesses).update({ active: b.active === false }).eq("id", b.id);
    if (error) throw new Error(errText(error));
  });
  const openBilling = (id) => {
    try { window.localStorage.setItem("semasa.view.billing.business", id); } catch { /* private window: the picker starts on the first business */ }
    go?.("bil");
  };

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6" data-businesses>
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6">
        <h1 className="font-display text-3xl">{t("Syarikat", "Businesses")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t("Setiap syarikat ada bil, nombor, letterhead, pelanggan dan kenalan CRM sendiri. Tambah syarikat baharu di sini; tetapkan letterhead dan bank di Bil → Tetapan.",
          "Each business has its own billing, numbers, letterhead, clients and CRM contacts. Add a new business here; set its letterhead and bank in Billing → Settings.")}</p>
      </motion.div>
      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/066_businesses.sql sekali.", "The table is not there yet: run supabase/066_businesses.sql once.")}</p>}
      {bizT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{bizT.error}</p>}

      <Card className="mb-6 p-5">
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); add(); }}>
          <label className="block min-w-0 flex-1"><Label>{t("Syarikat baharu", "New business")}</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder={t("Cth: Hermes Lab Sdn Bhd", "E.g. Hermes Lab Sdn Bhd")} data-new-business /></label>
          <Button type="submit" disabled={busy === "add" || missing || !name.trim()}><Plus size={14} /> {t("Tambah", "Add")}</Button>
        </form>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3 [&>*]:min-w-0">
        {rows.map((b) => {
          const off = b.active === false;
          const co = b.billing?.company || {};
          return (
            <Card key={b.id} className={`p-5 ${off ? "opacity-60" : ""}`} data-business-card={b.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  {renaming?.id === b.id ? (
                    <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); rename(); }}>
                      <Input value={renaming.name} onChange={(e) => setRenaming({ ...renaming, name: e.target.value })} maxLength={80} autoFocus />
                      <Button size="sm" type="submit"><Check size={12} /></Button>
                      <Button size="sm" variant="ghost" type="button" onClick={() => setRenaming(null)}><X size={12} /></Button>
                    </form>
                  ) : (
                    <h2 className="flex items-center gap-2 font-display text-xl"><Building2 size={16} className="text-accent" /> {b.name}
                      <button type="button" className="text-muted hover:text-ink" onClick={() => setRenaming({ id: b.id, name: b.name })} aria-label={t("Tukar nama", "Rename")}><Pencil size={12} /></button></h2>
                  )}
                  <p className="mt-0.5 truncate text-xs text-muted">{co.name || t("(tiada nama letterhead)", "(no letterhead name)")}{co.email ? ` · ${co.email}` : ""}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-muted">{[b.billing?.prefix?.quotation, b.billing?.prefix?.invoice, b.billing?.prefix?.receipt].filter(Boolean).join(" · ") || t("tiada awalan", "no prefixes")}</p>
                </div>
                {off && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted">{t("dimatikan", "off")}</span>}
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-tile bg-surface-2 p-2"><p className="font-display text-lg tabular-nums">{count(docsT.rows, b.id)}</p><p className="text-muted">{t("dokumen", "papers")}</p></div>
                <div className="rounded-tile bg-surface-2 p-2"><p className="font-display text-lg tabular-nums">{count(clientsT.rows, b.id)}</p><p className="text-muted">{t("pelanggan", "clients")}</p></div>
                <div className="rounded-tile bg-surface-2 p-2"><p className="font-display text-lg tabular-nums">{count(contactsT.rows, b.id)}</p><p className="text-muted">{t("kenalan CRM", "CRM contacts")}</p></div>
              </div>
              {!b.billing?.bank?.account_no && <p className="mt-3 text-xs text-warn">{t("Tiada akaun bank: invois tidak akan menunjukkan cara bayaran.", "No bank account: invoices will not show how to pay.")}</p>}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button size="sm" variant="soft" onClick={() => openBilling(b.id)} disabled={off}><Receipt size={12} /> {t("Bil & tetapan", "Billing & settings")}</Button>
                {b.id !== DEFAULT_BUSINESS && <Button size="sm" variant="ghost" onClick={() => toggle(b)} disabled={busy === `a-${b.id}`}>{off ? t("Hidupkan", "Switch on") : t("Matikan", "Switch off")}</Button>}
              </div>
            </Card>
          );
        })}
      </div>
    </main>
  );
}

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, Check, CreditCard, Pencil, Plus, Trash2, Wallet } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { fmtDate, money } from "../lib/billing";
import { CATEGORIES, CYCLES, STATUSES, blankSubscription, markPaid, standing, subsSummary, toRow, validateSubscription } from "../lib/subscriptions";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Modal, Select, TextArea } from "../components/ui/Field";

/* Langganan: the recurring bills (supabase/030_subscriptions.sql), in the shape of Wallos: what, who, how much, how often,
   and when the next payment is due. "Paid" steps next_payment forward by the cycle (lib/subscriptions.js markPaid); a
   row is never deleted by paying it. Overdue and due-this-week are computed from the date, not stored. */

const today = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);   // Malaysia's calendar day

export const CYCLE_WORDS = {
  daily: ["Harian", "Daily"], weekly: ["Mingguan", "Weekly"], monthly: ["Bulanan", "Monthly"], yearly: ["Tahunan", "Yearly"], one_time: ["Sekali", "One-time"],
};
const STATUS_WORDS = { active: ["Aktif", "Active"], paused: ["Dijeda", "Paused"], ended: ["Tamat", "Ended"] };
const CATEGORY_WORDS = {
  software: ["Perisian", "Software"], telco: ["Telko", "Telco"], utilities: ["Utiliti", "Utilities"], membership: ["Keahlian", "Membership"],
  insurance: ["Insurans", "Insurance"], finance: ["Kewangan", "Finance"], other: ["Lain", "Other"],
};
const STANDING = {
  overdue: { cls: "bg-danger/10 text-danger", bm: "Lewat", en: "Overdue" },
  due: { cls: "bg-warn/10 text-warn", bm: "Hampir", en: "Due soon" },
  ok: { cls: "bg-ok/10 text-ok", bm: "Aktif", en: "Active" },
  paused: { cls: "bg-surface-2 text-muted", bm: "Dijeda", en: "Paused" },
  ended: { cls: "bg-surface-2 text-muted", bm: "Tamat", en: "Ended" },
};

export default function SubscriptionsTab({ user, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (map, k) => (map[k] || [k, k])[L];
  const subsT = useTable(TABLES.subscriptions, { enabled: true, order: "next_payment", ascending: true, limit: 500 });
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState("");
  const [showEnded, setShowEnded] = useState(false);
  const day = today();
  const sum = useMemo(() => subsSummary(subsT.rows, day), [subsT.rows, day]);
  const rows = useMemo(() => subsT.rows
    .filter((s) => showEnded || s.status !== "ended")
    .map((s) => ({ ...s, standing: standing(s, day) }))
    .sort((a, b) => (a.next_payment || "9999").localeCompare(b.next_payment || "9999") || a.vendor.localeCompare(b.vendor)), [subsT.rows, showEnded, day]);
  const missing = /semasa_subscriptions/.test(subsT.error || "");

  async function save(form) {
    const bad = validateSubscription(form);
    if (bad.length) return onToast(t("Lengkapkan: {f}", "Fill in: {f}", { f: bad.join(", ") }), "danger");
    setBusy("save");
    try {
      const row = toRow(form);
      const q = form.id
        ? supabase.from(TABLES.subscriptions).update(row).eq("id", form.id)
        : supabase.from(TABLES.subscriptions).insert({ ...row, created_by: user?.id || null });
      const { error } = await q;
      if (error) throw new Error(errText(error));
      setEditing(null); subsT.reload();
      onToast(t("Disimpan.", "Saved."), "ok");
    } catch (e) { onToast(e.message, "danger"); } finally { setBusy(""); }
  }
  async function paid(s) {
    setBusy(s.id);
    try {
      const { error } = await supabase.from(TABLES.subscriptions).update(markPaid(s, day)).eq("id", s.id);
      if (error) throw new Error(errText(error));
      subsT.reload();
      onToast(t("Ditanda dibayar; tarikh seterusnya dikira.", "Marked paid; the next date is set."), "ok");
    } catch (e) { onToast(e.message, "danger"); } finally { setBusy(""); }
  }
  async function remove(s) {
    if (!window.confirm(t("Padam {n}?", "Delete {n}?", { n: `${s.vendor} · ${s.name}` }))) return;
    const { error } = await supabase.from(TABLES.subscriptions).delete().eq("id", s.id);
    if (error) return onToast(errText(error), "danger");
    subsT.reload(); onToast(t("Dipadam.", "Deleted."), "info");
  }

  const tiles = [
    { label: t("Sebulan (anggaran)", "Per month (estimate)"), value: money(sum.monthly, { currency: "MYR" }), icon: Wallet,
      hint: sum.unpriced ? t("{n} langganan tanpa nilai RM, tidak dikira", "{n} without an MYR figure, not counted", { n: sum.unpriced }) : t("{n} aktif", "{n} active", { n: sum.activeCount }) },
    { label: t("Perlu dibayar 30 hari", "Due in 30 days"), value: money(sum.due30, { currency: "MYR" }), icon: CalendarClock, hint: t("{n} bil", "{n} bills", { n: sum.due30Count }) },
    { label: t("Lewat", "Overdue"), value: money(sum.overdue, { currency: "MYR" }), icon: AlertTriangle, hint: t("{n} bil", "{n} bills", { n: sum.overdueCount }), tone: sum.overdueCount ? "danger" : "" },
    { label: t("Minggu ini", "This week"), value: String(sum.soon), icon: CreditCard, hint: t("bil dalam 7 hari", "bills within 7 days") },
  ];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Langganan", "Subscriptions")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Bil berulang perniagaan dan peribadi: apa, siapa, berapa dan bila seterusnya. Tekan Dibayar dan tarikh seterusnya dikira ikut kitaran.",
            "Recurring bills, business and personal: what, who, how much and when next. Press Paid and the next date steps forward by the cycle.")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => setShowEnded((v) => !v)}>{showEnded ? t("Sembunyi yang tamat", "Hide ended") : t("Tunjuk yang tamat", "Show ended")}</Button>
          <Button onClick={() => setEditing(blankSubscription(day))}><Plus size={14} /> {t("Tambah", "Add")}</Button>
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/030_subscriptions.sql sekali.", "The table is not there yet: run supabase/030_subscriptions.sql once.")}</p>}
      {subsT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{subsT.error}</p>}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((s) => (
          <Card key={s.label} className={`p-4 ${s.tone === "danger" ? "border-danger/40" : ""}`}>
            <div className="flex items-center justify-between"><span className="text-[11px] uppercase tracking-widest text-muted">{s.label}</span><s.icon size={16} className="text-muted" /></div>
            <p className={`mt-2 font-display text-2xl tabular-nums ${s.tone === "danger" ? "text-danger" : ""}`}>{s.value}</p>
            <p className="mt-0.5 text-xs text-muted">{s.hint}</p>
          </Card>
        ))}
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] uppercase tracking-widest text-muted">
            <tr>
              <th className="px-4 py-3">{t("Langganan", "Subscription")}</th>
              <th className="px-3 py-3">{t("Jumlah", "Amount")}</th>
              <th className="px-3 py-3">{t("Kitaran", "Cycle")}</th>
              <th className="px-3 py-3">{t("Seterusnya", "Next")}</th>
              <th className="px-3 py-3">{t("Status", "Status")}</th>
              <th className="px-3 py-3">{t("Bayaran", "Payment")}</th>
              <th className="px-3 py-3" />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const st = STANDING[s.standing];
              return (
                <tr key={s.id} className="border-t border-line/70 align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium">{s.vendor} <span className="text-muted">·</span> {s.name}</div>
                    <div className="text-xs text-muted">{w(CATEGORY_WORDS, s.category)}{s.account_ref ? ` · ${s.account_ref}` : ""}</div>
                    {s.notes && <div className="mt-1 max-w-md text-xs text-muted">{s.notes}</div>}
                  </td>
                  <td className="px-3 py-3 tabular-nums">
                    {money(s.amount, { currency: s.currency })}
                    {s.amount_myr != null && s.currency !== "MYR" && <div className="text-xs text-muted">≈ {money(s.amount_myr, { currency: "MYR" })}</div>}
                  </td>
                  <td className="px-3 py-3">{w(CYCLE_WORDS, s.cycle)}</td>
                  <td className="px-3 py-3 tabular-nums">{s.next_payment ? fmtDate(s.next_payment) : "—"}
                    {s.last_paid && <div className="text-xs text-muted">{t("dibayar", "paid")} {fmtDate(s.last_paid)}</div>}</td>
                  <td className="px-3 py-3"><span className={`rounded-pill px-2 py-0.5 text-[11px] ${st.cls}`}>{L ? st.en : st.bm}</span></td>
                  <td className="px-3 py-3 text-xs text-muted">{s.auto_pay ? t("Auto", "Auto") : t("Manual", "Manual")}{s.payment_method ? ` · ${s.payment_method}` : ""}</td>
                  <td className="px-3 py-3">
                    <div className="flex justify-end gap-1">
                      {s.status !== "ended" && <Button size="sm" variant="ghost" disabled={busy === s.id} onClick={() => paid(s)} title={t("Tanda dibayar", "Mark paid")}><Check size={13} /></Button>}
                      <Button size="sm" variant="ghost" onClick={() => setEditing({ ...blankSubscription(day), ...s, amount: String(s.amount), amount_myr: s.amount_myr ?? "", next_payment: s.next_payment || "", last_paid: s.last_paid || "" })} title={t("Sunting", "Edit")}><Pencil size={13} /></Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(s)} title={t("Padam", "Delete")}><Trash2 size={13} /></Button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!rows.length && !subsT.loading && <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">{t("Tiada langganan lagi. Tekan Tambah.", "No subscriptions yet. Press Add.")}</td></tr>}
          </tbody>
        </table>
      </Card>

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title={editing?.id ? t("Sunting langganan", "Edit subscription") : t("Langganan baharu", "New subscription")}>
        {editing && <SubscriptionForm form={editing} setForm={setEditing} onSave={() => save(editing)} busy={busy === "save"} t={t} w={w} />}
      </Modal>
    </main>
  );
}

function SubscriptionForm({ form, setForm, onSave, busy, t, w }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e });
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); onSave(); }}>
      <label><Label>{t("Pembekal", "Vendor")}</Label><Input value={form.vendor} onChange={set("vendor")} placeholder="Anthropic" /></label>
      <label><Label>{t("Nama", "Name")}</Label><Input value={form.name} onChange={set("name")} placeholder="Claude Max 5x" /></label>
      <label><Label>{t("Jumlah", "Amount")}</Label><Input type="number" step="0.01" min="0" value={form.amount} onChange={set("amount")} /></label>
      <label><Label>{t("Mata wang", "Currency")}</Label><Input value={form.currency} onChange={set("currency")} maxLength={3} /></label>
      <label><Label>{t("Nilai RM (bil asing)", "MYR charged (foreign bill)")} </Label><Input type="number" step="0.01" min="0" value={form.amount_myr} onChange={set("amount_myr")} placeholder={t("kosong = sama", "blank = same")} /></label>
      <label><Label>{t("Kitaran", "Cycle")}</Label><Select className="w-full" value={form.cycle} onChange={set("cycle")} options={CYCLES.map((c) => [c, w(CYCLE_WORDS, c)])} /></label>
      <label><Label>{t("Bayaran seterusnya", "Next payment")}</Label><Input type="date" value={form.next_payment} onChange={set("next_payment")} /></label>
      <label><Label>{t("Terakhir dibayar", "Last paid")}</Label><Input type="date" value={form.last_paid} onChange={set("last_paid")} /></label>
      <label><Label>{t("Status", "Status")}</Label><Select className="w-full" value={form.status} onChange={set("status")} options={STATUSES.map((s) => [s, w(STATUS_WORDS, s)])} /></label>
      <label><Label>{t("Kategori", "Category")}</Label><Select className="w-full" value={form.category} onChange={set("category")} options={CATEGORIES.map((c) => [c, w(CATEGORY_WORDS, c)])} /></label>
      <label><Label>{t("Cara bayar", "Payment method")}</Label><Input value={form.payment_method} onChange={set("payment_method")} placeholder="Visa ...5742" /></label>
      <label><Label>{t("Rujukan akaun", "Account reference")}</Label><Input value={form.account_ref} onChange={set("account_ref")} /></label>
      <label className="sm:col-span-2"><Label>{t("Pautan bayar / urus", "Pay / manage link")}</Label><Input value={form.url} onChange={set("url")} placeholder="https://" /></label>
      <label className="sm:col-span-2"><Label>{t("Nota", "Notes")}</Label><TextArea rows={2} value={form.notes} onChange={set("notes")} /></label>
      <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={Boolean(form.auto_pay)} onChange={set("auto_pay")} /> {t("Dibayar automatik (kad / debit terus)", "Paid automatically (card / direct debit)")}</label>
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button type="submit" disabled={busy}>{t("Simpan", "Save")}</Button>
      </div>
    </form>
  );
}

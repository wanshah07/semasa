import { useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Camera, ExternalLink, FolderOpen, Pencil, RefreshCw, Trash2, Upload, Wallet } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { stampMYT } from "../lib/format";
import { fmtDate, money } from "../lib/billing";
import { removeReference, shrinkPhoto, uploadReference } from "../lib/storage";
import { markPaid } from "../lib/subscriptions";
import { CATEGORIES, CATEGORY_WORDS, STATUS_WORDS, byMonth, fileLabel, receiptRow, receiptsSummary, validateReceipt } from "../lib/receipts";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Modal, Select, TextArea } from "../components/ui/Field";

/* Resit (supabase/033_receipts.sql): snap or upload a receipt; the picture goes to the bucket and a pending row wakes the
   worker (backend/semasa/receipts.py), which reads it with the vision model, files it in Google Drive under
   Semasa/Resit/<YYYY>/<MM> and matches the vendor to a subscription. This page shows the result by month and category and
   lets Wan correct any field; nothing here reads a picture itself. */

const today = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
const STATUS_TONE = { pending: "bg-accent/10 text-accent", working: "bg-accent/10 text-accent", done: "bg-ok/10 text-ok", error: "bg-danger/10 text-danger" };
const MONTHS_BM = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogos", "Sep", "Okt", "Nov", "Dis"];
const MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function ResitTab({ user, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (map, k) => (map[k] || [k, k])[L];
  const rowsT = useTable(TABLES.receipts, { enabled: true, order: "created_at", limit: 2000 });
  const subsT = useTable(TABLES.subscriptions, { enabled: true, order: "vendor", ascending: true, limit: 500, realtime: false });
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState("");
  const camRef = useRef(null);
  const fileRef = useRef(null);
  const day = today();
  const missing = /semasa_receipts/.test(rowsT.error || "");
  const sum = useMemo(() => receiptsSummary(rowsT.rows, day), [rowsT.rows, day]);
  const groups = useMemo(() => byMonth(rowsT.rows.filter((r) => !filter || r.category === filter)), [rowsT.rows, filter]);
  const monthName = (k) => (/^\d{4}-\d{2}$/.test(k) ? `${(L ? MONTHS_EN : MONTHS_BM)[Number(k.slice(5, 7)) - 1]} ${k.slice(0, 4)}` : k);
  const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { onToast(e.message || String(e), "danger"); } };

  const snap = guard(async (file) => {
    if (!file) return;
    if (!/^image\//.test(file.type)) return onToast(t("Pilih gambar (JPG/PNG/HEIC).", "Choose a picture (JPG/PNG/HEIC)."), "danger");
    setBusy("upload");
    try {
      // 1600px keeps the small print on a receipt legible for the reader and stays around a megabyte
      const small = await shrinkPhoto(file, 1600);
      const up = await uploadReference(user, small);
      const { data } = supabase.storage.from("semasa-reference").getPublicUrl(up.path);
      const { error } = await supabase.from(TABLES.receipts).insert({ image_path: up.path, image_url: data.publicUrl, status: "pending", created_by: user?.id || null });
      if (error) throw new Error(/semasa_receipts/.test(errText(error)) ? t("Jadual belum ada: jalankan supabase/033_receipts.sql sekali.", "The table is not there yet: run supabase/033_receipts.sql once.") : errText(error));
      onToast(t("Dimuat naik. Pembaca membaca dan memfailkannya dalam seminit dua.", "Uploaded. The reader reads and files it within a minute or two."), "ok");
      rowsT.reload();
    } finally { setBusy(""); if (camRef.current) camRef.current.value = ""; if (fileRef.current) fileRef.current.value = ""; }
  });
  const save = guard(async (form) => {
    const bad = validateReceipt(form);
    if (bad.length) return onToast(t("Semak: {f}", "Check: {f}", { f: bad.join(", ") }), "danger");
    const { error } = await supabase.from(TABLES.receipts).update(receiptRow(form)).eq("id", form.id);
    if (error) throw new Error(errText(error));
    setEditing(null); rowsT.reload(); onToast(t("Disimpan.", "Saved."), "ok");
  });
  const reread = guard(async (r) => {
    const { error } = await supabase.from(TABLES.receipts).update({ status: "pending", attempts: 0, error: "" }).eq("id", r.id);
    if (error) throw new Error(errText(error));
    rowsT.reload(); onToast(t("Dihantar semula kepada pembaca.", "Sent back to the reader."), "ok");
  });
  const remove = guard(async (r) => {
    if (!window.confirm(t("Padam resit ini dari Semasa? Salinan di Google Drive kekal.", "Delete this receipt from Semasa? The Google Drive copy stays."))) return;
    const { error } = await supabase.from(TABLES.receipts).delete().eq("id", r.id);
    if (error) throw new Error(errText(error));
    try { await removeReference(r.image_path); } catch { /* the bucket copy is not the record */ }
    rowsT.reload(); onToast(t("Dipadam.", "Deleted."), "info");
  });
  const paySubscription = guard(async (r) => {
    const s = subsT.rows.find((x) => x.id === r.subscription_id);
    if (!s) return;
    const { error } = await supabase.from(TABLES.subscriptions).update(markPaid(s, r.doc_date || day)).eq("id", s.id);
    if (error) throw new Error(errText(error));
    subsT.reload(); onToast(t("{v} ditanda dibayar; tarikh seterusnya dikira.", "{v} marked paid; the next date is set.", { v: s.vendor }), "ok");
  });

  const tiles = [
    { label: t("Bulan ini", "This month"), value: money(sum.monthTotal, { currency: "MYR" }), icon: Wallet, hint: t("{n} resit", "{n} receipts", { n: sum.monthCount }) },
    { label: t("Menunggu pembaca", "Waiting for the reader"), value: String(sum.pending), icon: RefreshCw, hint: sum.failed ? t("{n} gagal", "{n} failed", { n: sum.failed }) : t("tiada yang gagal", "none failed"), tone: sum.failed ? "danger" : "" },
    { label: t("Belum difailkan", "Not filed yet"), value: String(sum.unfiled), icon: FolderOpen, hint: t("dibaca tetapi belum di Drive", "read but not in Drive yet"), tone: sum.unfiled ? "warn" : "" },
    { label: t("Perlu semakan", "Needs a look"), value: String(sum.lowConfidence), icon: AlertTriangle, hint: t("pembaca kurang pasti", "the reader was unsure"), tone: sum.lowConfidence ? "warn" : "" },
  ];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Resit", "Receipts")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Snap resit; gambar masuk Google Drive (Semasa/Resit/tahun/bulan), AI baca kedai, tarikh, jumlah dan butiran, dan susun ikut bulan dan kategori. Betulkan mana-mana medan jika pembaca tersilap.",
            "Snap a receipt; the picture goes to Google Drive (Semasa/Resit/year/month), the AI reads the shop, date, total and items, and files it by month and category. Correct any field the reader got wrong.")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={camRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => snap(e.target.files?.[0])} />
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => snap(e.target.files?.[0])} />
          <Button variant="ghost" disabled={Boolean(busy)} onClick={() => fileRef.current?.click()}><Upload size={14} /> {t("Muat naik", "Upload")}</Button>
          <Button disabled={Boolean(busy)} onClick={() => camRef.current?.click()}><Camera size={14} /> {busy === "upload" ? t("Memuat naik…", "Uploading…") : t("Snap resit", "Snap a receipt")}</Button>
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/033_receipts.sql sekali.", "The table is not there yet: run supabase/033_receipts.sql once.")}</p>}
      {rowsT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{rowsT.error}</p>}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((s) => (
          <Card key={s.label} className={`p-4 ${s.tone === "danger" ? "border-danger/40" : s.tone === "warn" ? "border-warn/40" : ""}`}>
            <div className="flex items-center justify-between"><span className="text-[11px] uppercase tracking-widest text-muted">{s.label}</span><s.icon size={16} className="text-muted" /></div>
            <p className={`mt-2 font-display text-2xl tabular-nums ${s.tone === "danger" ? "text-danger" : ""}`}>{s.value}</p>
            <p className="mt-0.5 text-xs text-muted">{s.hint}</p>
          </Card>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap gap-1">
        <button type="button" onClick={() => setFilter("")} className={`rounded-pill px-3 py-1 text-xs ${!filter ? "bg-ink text-surface" : "bg-surface-2 text-muted"}`}>{t("Semua", "All")}</button>
        {CATEGORIES.map((c) => <button type="button" key={c} onClick={() => setFilter(c)} className={`rounded-pill px-3 py-1 text-xs ${filter === c ? "bg-ink text-surface" : "bg-surface-2 text-muted"}`}>{w(CATEGORY_WORDS, c)}</button>)}
      </div>

      {groups.map((g) => (
        <section key={g.month} className="mb-8">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-xl">{monthName(g.month)}</h2>
            <p className="text-sm text-muted"><span className="font-mono tabular-nums text-ink">{money(g.total, { currency: "MYR" })}</span> · {g.rows.length} {t("resit", "receipts")}
              {g.foreign ? ` · ${t("{n} mata wang asing tidak dikira", "{n} in a foreign currency not counted", { n: g.foreign })}` : ""}
              {g.unread ? ` · ${t("{n} belum dibaca", "{n} not read yet", { n: g.unread })}` : ""}</p>
          </div>
          <div className="mb-3 flex flex-wrap gap-2 text-[11px] text-muted">
            {Object.entries(g.byCategory).sort((a, b) => b[1] - a[1]).map(([c, v]) => <span key={c} className="rounded-pill bg-surface-2 px-2 py-0.5">{w(CATEGORY_WORDS, c)} <span className="font-mono tabular-nums text-ink">{money(v)}</span></span>)}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {g.rows.map((r) => (
              <Card key={r.id} className="flex gap-3 p-3">
                <a href={r.image_url} target="_blank" rel="noreferrer" className="shrink-0"><img src={r.image_url} alt="" loading="lazy" className="h-24 w-20 rounded-tile object-cover" /></a>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate font-medium">{r.vendor || t("(belum dibaca)", "(not read yet)")}</p>
                    <span className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] ${STATUS_TONE[r.status]}`}>{w(STATUS_WORDS, r.status)}</span>
                  </div>
                  <p className="font-mono text-sm tabular-nums">{r.total != null ? money(r.total, { currency: r.currency || "MYR" }) : "—"}{r.doc_date ? <span className="ml-2 text-xs text-muted">{fmtDate(r.doc_date)}</span> : null}</p>
                  <p className="text-xs text-muted">{w(CATEGORY_WORDS, r.category || "lain")}{r.payment_method && r.payment_method !== "unknown" ? ` · ${r.payment_method}` : ""}{r.confidence != null && r.confidence < 0.6 ? ` · ${t("kurang pasti", "unsure")}` : ""}</p>
                  {r.summary && <p className="mt-1 line-clamp-2 text-xs text-ink/80">{r.summary}</p>}
                  {r.error && <p className="mt-1 text-[11px] text-danger">{r.error}</p>}
                  {r.subscription_id && subsT.rows.find((s) => s.id === r.subscription_id) && (
                    <p className="mt-1 text-[11px] text-muted">{t("Langganan: {v}", "Subscription: {v}", { v: subsT.rows.find((s) => s.id === r.subscription_id).vendor })} · <button type="button" className="underline" onClick={() => paySubscription(r)}>{t("tanda dibayar", "mark paid")}</button></p>
                  )}
                  <div className="mt-2 flex flex-wrap gap-1">
                    {r.drive_url ? <a href={r.drive_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-2 py-1 text-[11px] text-muted hover:text-ink" title={r.drive_path}><ExternalLink size={11} /> Drive</a> : null}
                    <Button size="sm" variant="ghost" onClick={() => setEditing({ ...r, total: r.total ?? "", tax: r.tax ?? "", doc_date: r.doc_date || "", subscription_id: r.subscription_id || "" })} title={t("Betulkan", "Correct")}><Pencil size={12} /></Button>
                    {r.status !== "pending" && <Button size="sm" variant="ghost" onClick={() => reread(r)} title={t("Baca semula", "Read again")}><RefreshCw size={12} /></Button>}
                    <Button size="sm" variant="ghost" onClick={() => remove(r)} title={t("Padam", "Delete")}><Trash2 size={12} /></Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}
      {!groups.length && !rowsT.loading && <p className="py-10 text-center text-sm text-muted">{t("Tiada resit lagi. Tekan Snap resit.", "No receipts yet. Press Snap a receipt.")}</p>}
      <p className="mt-6 text-[11px] text-muted">{t("Tarikh ialah tarikh pada resit; jika tidak terbaca, bulan ia disnap. Jumlah dalam mata wang asing tidak ditukar.", "The date is the one on the receipt; when unreadable, the month it was snapped. Foreign-currency totals are not converted.")} · {rowsT.rows.length ? stampMYT(rowsT.rows[0].created_at) : ""}</p>

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title={editing ? fileLabel(editing) : ""}>
        {editing && (
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save(editing); }}>
            <label className="sm:col-span-2"><Label>{t("Kedai / pembekal", "Shop / vendor")}</Label><Input value={editing.vendor || ""} onChange={(e) => setEditing({ ...editing, vendor: e.target.value })} /></label>
            <label><Label>{t("Tarikh", "Date")}</Label><Input type="date" value={editing.doc_date} onChange={(e) => setEditing({ ...editing, doc_date: e.target.value })} /></label>
            <label><Label>{t("Kategori", "Category")}</Label><Select className="w-full" value={editing.category || "lain"} onChange={(v) => setEditing({ ...editing, category: v })} options={CATEGORIES.map((c) => [c, w(CATEGORY_WORDS, c)])} /></label>
            <label><Label>{t("Jumlah", "Total")}</Label><Input type="number" step="0.01" min="0" value={editing.total} onChange={(e) => setEditing({ ...editing, total: e.target.value })} /></label>
            <label><Label>{t("Mata wang", "Currency")}</Label><Input value={editing.currency || "MYR"} maxLength={3} onChange={(e) => setEditing({ ...editing, currency: e.target.value })} /></label>
            <label><Label>{t("Cukai (SST)", "Tax (SST)")}</Label><Input type="number" step="0.01" min="0" value={editing.tax} onChange={(e) => setEditing({ ...editing, tax: e.target.value })} /></label>
            <label><Label>{t("Cara bayar", "Payment method")}</Label><Select className="w-full" value={editing.payment_method || "unknown"} onChange={(v) => setEditing({ ...editing, payment_method: v })} options={[["unknown", "—"], ["cash", t("Tunai", "Cash")], ["card", t("Kad", "Card")], ["ewallet", "e-Wallet"], ["transfer", t("Pindahan", "Transfer")]]} /></label>
            <label className="sm:col-span-2"><Label>{t("Langganan berkaitan", "Related subscription")}</Label><Select className="w-full" value={editing.subscription_id} onChange={(v) => setEditing({ ...editing, subscription_id: v })} options={[["", "—"], ...subsT.rows.map((s) => [s.id, `${s.vendor} · ${s.name}`])]} /></label>
            <label className="sm:col-span-2"><Label>{t("Ringkasan", "Summary")}</Label><TextArea rows={2} value={editing.summary || ""} onChange={(e) => setEditing({ ...editing, summary: e.target.value })} /></label>
            {Array.isArray(editing.items) && editing.items.length ? <div className="rounded-tile border border-line p-3 text-xs sm:col-span-2">
              <p className="mb-1 text-[11px] uppercase tracking-widest text-muted">{t("Butiran yang dibaca", "Items read")}</p>
              <ul className="space-y-0.5">{editing.items.map((it, i) => <li key={i} className="flex justify-between gap-2"><span className="truncate">{it.qty && it.qty !== 1 ? `${it.qty} × ` : ""}{it.name}</span><span className="font-mono tabular-nums">{it.price != null ? money(it.price) : ""}</span></li>)}</ul>
            </div> : null}
            <label className="sm:col-span-2"><Label>{t("Nota", "Notes")}</Label><Input value={editing.notes || ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} /></label>
            <div className="flex justify-end gap-2 sm:col-span-2"><Button type="submit">{t("Simpan", "Save")}</Button></div>
          </form>
        )}
      </Modal>
    </main>
  );
}

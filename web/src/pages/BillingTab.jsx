import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Bell, Briefcase, Building2, Check, Copy, Download, Eye, FileText, Link2, Mail, Pencil, Plus, Printer, Receipt,
  Send, Settings2, Trash2, Users, Wallet, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { useLang } from "../lib/i18n";
import { stampMYT } from "../lib/format";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useTable } from "../lib/hooks";
import {
  DEFAULT_OFFSETS, KINDS, OPEN, PROJECT_STATUS, addDays, billingSettings, calcTotals, clientSnapshot, effectiveStatus, emailFor,
  emailOf, fileName, fmtDate, invoiceFromQuotation, isoDate, kindLabel, money, nextReminder, numberPreview, projectSummary, publicLink,
  receiptFromInvoice, statusLabel, summary, validEmail, validateDoc, weeklySeries, projectProgress,
} from "../lib/billing";
import { documentHtml, pagesHtml } from "../lib/billingDoc";
import { qrDataUrl } from "../lib/qr";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Segmented, Select, TextArea } from "../components/ui/Field";
import DocumentsTable from "@/components/ui/table-2";
import App1 from "@/components/ui/app-1";
import { Timeline, TimelineContent, TimelineDate, TimelineHeader, TimelineIndicator, TimelineItem, TimelineSeparator, TimelineTitle } from "@/components/ui/timeline";

/* Bil (Wan, 7 Oct 2026: "create feature for quotation, invoice and receipt, can auto send email, view, download, send
   reminder, status ... create the dashboard to overview"). One place for the three papers WS Regulab Solutions sends:
     - a dashboard: what is outstanding, what is overdue (and how old), what was paid this month, which quotations are open;
     - the table (components/ui/table-2.tsx): every document, searchable, sortable, with its derived status and actions;
     - an editor for drafts, a viewer for issued papers (preview, timeline of what happened, e-mails and their outcome);
     - clients (one record, copied onto each paper when it is issued) and the settings (company, bank, numbering, terms, e-mail).
   Rules, in one place (web/src/lib/billing.js): a number is allocated by the database on ISSUE and never reused; an issued
   paper's words never change (a mistake is voided and reissued); e-mail goes out from the worker (Gmail via Composio),
   never from this page, so a Send here is a row in the outbox and the outcome arrives in the timeline. */

const MYT = "Asia/Kuala_Lumpur";
const STATES = ["Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang", "Perak", "Perlis", "Pulau Pinang", "Sabah", "Sarawak", "Selangor",
  "Terengganu", "W.P. Kuala Lumpur", "W.P. Labuan", "W.P. Putrajaya"];
const METHODS = { bm: ["Pindahan bank", "DuitNow", "Tunai", "Cek", "Kad", "Lain-lain"], en: ["Bank transfer", "DuitNow", "Cash", "Cheque", "Card", "Other"] };
const BLANK_CLIENT = { name: "", reg_no: "", attention: "", email: "", phone: "", address: "", postcode: "", city: "", state: "", country: "Malaysia", lang: "en", notes: "" };
const initialsOf = (name) => String(name || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";
const nowIso = () => new Date().toISOString();

export default function BillingTab({ user, settings, save, onToast }) {
  const { t, lang } = useLang();
  const docsT = useTable(TABLES.billingDocs, { enabled: true, limit: 2000 });
  const clientsT = useTable(TABLES.clients, { enabled: true, order: "name", ascending: true, limit: 2000, realtime: false });
  const projectsT = useTable(TABLES.projects, { enabled: true, order: "created_at", limit: 2000, realtime: false });
  const countersT = useTable(TABLES.billingCounters, { enabled: true, order: "year", limit: 50, realtime: false });
  const eventsT = useTable(TABLES.billingEvents, { enabled: true, order: "at", limit: 400 });
  const outboxT = useTable(TABLES.billingOutbox, { enabled: true, order: "created_at", limit: 200 });
  const cfg = useMemo(() => billingSettings(settings?.billing), [settings]);
  const ready = settings && typeof settings.billing === "object" && settings.billing !== null;
  const notSetUp = /semasa_billing|semasa_clients/.test(docsT.error || clientsT.error || "");
  const today = isoDate();
  const docs = docsT.rows;
  const clients = clientsT.rows;
  const projects = projectsT.rows;
  const projectName = (id) => projects.find((p) => p.id === id)?.name || "";

  const [kind, setKind] = useState("all");
  const [editing, setEditing] = useState(null);        // a draft (new or existing) in the editor
  const [viewing, setViewing] = useState(null);        // an issued document in the viewer
  const [sending, setSending] = useState(null);        // { doc, action }
  const [paying, setPaying] = useState(null);          // { docs: [...] }
  const [clientsOpen, setClientsOpen] = useState(false);
  const [projectsOpen, setProjectsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [printing, setPrinting] = useState("");        // html being printed through the hidden frame

  const reload = useCallback(() => { docsT.reload(); eventsT.reload(); outboxT.reload(); countersT.reload(); }, [docsT, eventsT, outboxT, countersT]);
  const sum = useMemo(() => summary(docs, today), [docs, today]);
  const weekly = useMemo(() => weeklySeries(docs, today, 8), [docs, today]);
  const overviewProjects = useMemo(() => projects
    .filter((p) => !["done", "cancelled"].includes(p.status))
    .sort((a, b) => String(a.end_date || "9999").localeCompare(String(b.end_date || "9999")))
    .slice(0, 6)
    .map((p) => {
      const m = projectSummary(p.id, docs, today);
      const L = lang === "en" ? "en" : "bm";
      const badge = p.status === "active" ? "default" : p.status === "on_hold" ? "destructive" : "secondary";
      const desc = m.invoiced > 0
        ? t("Dibayar {a} daripada {b}{c}", "Paid {a} of {b}{c}", { a: money(m.paid), b: money(m.invoiced), c: m.overdue > 0 ? ` · ${t("lewat", "overdue")} ${money(m.overdue)}` : "" })
        : m.quoted > 0 ? t("Disebut harga {a}, belum diinvois", "Quoted {a}, not invoiced yet", { a: money(m.quoted) }) : t("Belum ada kertas", "No papers yet");
      const client = clients.find((c) => c.id === p.client_id);
      return { id: p.id, name: p.name, description: desc, progress: projectProgress(p, docs, today), status: PROJECT_STATUS[p.status]?.[L] || p.status, badge,
        due: p.end_date ? fmtDate(p.end_date) : "", team: client ? [{ name: client.name, initials: initialsOf(client.name) }] : [], onClick: () => setProjectsOpen(true) };
    }), [projects, docs, clients, today, lang, t]);
  const overviewActivity = useMemo(() => eventsT.rows.slice(0, 12).map((ev) => {
    const d = docs.find((x) => x.id === ev.doc_id);
    const who = d?.client?.name || t("(tiada pelanggan)", "(no client)");
    return { id: ev.id, person: { name: who, initials: initialsOf(who) }, action: `${d?.number || "—"} · ${eventLabel(ev, t)}`, time: stampMYT(ev.at), onClick: d ? () => setViewing(d) : undefined };
  }), [eventsT.rows, docs, t]);
  const site = `${window.location.origin}${window.location.pathname}`;
  const base = `${import.meta.env.BASE_URL}cards/`;
  const abs = (p) => new URL(p, window.location.href).href;
  const htmlOf = useCallback((d) => documentHtml({ ...d, project: projectName(d.project_id), parent_number: docs.find((x) => x.id === d.parent_id)?.number || "" }, cfg, { logoUrl: abs(`${base}logo-ink.png`), fontsCss: abs(`${base}fonts.css`),
    qr: d.token ? qrDataUrl(publicLink(d.token, site)) : "" }), [cfg, base, site, projects, docs]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ---- words for the table ---------------------------------------------------------------------------------------------------
  const words = useMemo(() => ({
    title: t("Dokumen", "Documents"), subtitle: t("Sebut harga, invois dan resit, terkini dahulu.", "Quotations, invoices and receipts, newest first."),
    company: cfg.company.name || "WS Regulab Solutions", outstanding: t("Belum dijelaskan", "Outstanding"),
    filter: t("Tapis: pelanggan, nombor, rujukan…", "Filter: client, number, reference…"), results: (n) => t(n === 1 ? "hasil" : "hasil", n === 1 ? "result" : "results"),
    selected: t("dipilih", "selected"), clear: t("Kosongkan", "Clear"), download: t("Muat turun", "Download"), reminder: t("Hantar peringatan", "Send reminder"),
    markPaid: t("Tanda dibayar", "Mark as paid"), none: t("Tiada dokumen sepadan.", "No documents match."),
    docs: (n) => t("{n} dokumen", n === 1 ? "{n} document" : "{n} documents", { n }), page: (a, b) => t("Halaman {a} / {b}", "Page {a} of {b}", { a, b }),
    columns: { number: t("Nombor", "Number"), client: t("Pelanggan", "Client"), reference: t("Rujukan", "Reference"), issued: t("Dikeluarkan", "Issued"),
      due: t("Tarikh akhir", "Due"), status: t("Status", "Status"), amount: t("Jumlah", "Amount") },
    kinds: Object.fromEntries(KINDS.map((k) => [k, kindLabel(k, lang)])),
    statuses: Object.fromEntries(["draft", "issued", "sent", "viewed", "accepted", "declined", "expired", "converted", "paid", "void", "overdue"].map((s) => [s, statusLabel(s, lang)])),
    actions: { view: t("Lihat", "View"), edit: t("Sunting draf", "Edit draft"), download: t("Muat turun PDF", "Download PDF"), send: t("Hantar e-mel", "Send e-mail"),
      reminder: t("Hantar peringatan", "Send reminder"), paid: t("Tanda dibayar → resit", "Mark paid → receipt"), convert: t("Jadikan invois", "Convert to invoice"),
      void: t("Batalkan", "Void"), delete: t("Padam draf", "Delete draft"), link: t("Salin pautan awam", "Copy public link"), duplicate: t("Salin sebagai draf baharu", "Duplicate as new draft"),
      accepted: t("Tanda diterima", "Mark accepted"), declined: t("Tanda ditolak", "Mark declined") },
    footer: t("Angka dalam MYR. Status Lewat dan Luput dikira daripada tarikh, bukan disimpan.", "Figures in MYR. Overdue and Expired are derived from the dates, never stored."),
  }), [t, lang, cfg.company.name]);

  const rows = useMemo(() => docs
    .filter((d) => kind === "all" || d.kind === kind)
    .map((d) => ({ id: d.id, kind: d.kind, number: d.number, status: d.status, effective: effectiveStatus(d, today), client: d.client?.name || t("(tiada pelanggan)", "(no client)"),
      initials: initialsOf(d.client?.name), reference: projectName(d.project_id) || d.reference || (d.kind === "receipt" ? parentNumber(d) : ""), total: Number(d.total) || 0,
      currency: d.currency || "MYR", issue_date: d.issue_date, due_date: d.due_date, sent_at: d.sent_at, viewed_at: d.viewed_at, pdf_url: d.pdf_url })),
  [docs, kind, today, t, projects]);   // eslint-disable-line react-hooks/exhaustive-deps
  function parentNumber(d) { return docs.find((x) => x.id === d.parent_id)?.number || ""; }

  // ---- writes ----------------------------------------------------------------------------------------------------------------
  async function logEvent(doc_id, k, detail = {}) {
    await supabase.from(TABLES.billingEvents).insert({ doc_id, kind: k, detail, actor: user?.id || null });
  }
  async function patchDoc(id, patch) {
    const { data, error } = await supabase.from(TABLES.billingDocs).update(patch).eq("id", id).select("*");
    if (error) throw new Error(errText(error));
    return data?.[0];
  }
  async function enqueue(doc, action, { to, cc = [], subject = "", body = "", meta = {} } = {}) {
    const addr = String(to || emailOf(doc, clients.find((c) => c.id === doc.client_id))).trim();
    if (!validEmail(addr)) throw new Error(t("Pelanggan ini tiada alamat e-mel yang sah.", "This client has no valid e-mail address."));
    const { error } = await supabase.from(TABLES.billingOutbox).insert({ doc_id: doc.id, action, to_email: addr, cc, subject, body, lang: doc.lang || "bm",
      meta, created_by: user?.id || null });
    if (error) throw new Error(errText(error));
  }
  function guard(fn) {
    return async (...a) => {
      setBusy("1");
      try { await fn(...a); reload(); }
      catch (e) { onToast(e?.message || String(e), "danger"); }
      finally { setBusy(""); }
    };
  }

  const newDraft = (k, from = {}) => {
    const c = clients.find((x) => x.id === from.client_id);
    setEditing({ kind: k, status: "draft", client_id: from.client_id || null, project_id: from.project_id || null, client: from.client || (c ? clientSnapshot(c) : {}), items: from.items || [{ description: "", qty: 1, rate: "" }],
      currency: "MYR", tax_rate: from.tax_rate ?? cfg.tax_rate, discount: from.discount || 0, issue_date: today,
      due_date: k === "receipt" ? null : addDays(today, k === "quotation" ? cfg.days.quotation_valid : cfg.days.invoice_due),
      terms: from.terms ?? cfg.terms[k] ?? "", notes: from.notes || "", reference: from.reference || "", lang: from.lang || c?.lang || cfg.lang,
      payment: k === "receipt" ? { method: METHODS[lang][0], date: today, reference: "" } : {}, parent_id: from.parent_id || null, ...(from.id ? { id: from.id } : {}) });
  };

  const saveDraft = guard(async (d, { issue = false, send = false } = {}) => {
    const totals = calcTotals(d.items, { tax_rate: d.tax_rate, discount: d.discount });
    const items = d.items.filter((it) => String(it.description || "").trim() || Number(it.rate) || Number(it.qty) !== 1)
      .map((it) => ({ description: String(it.description || "").trim(), detail: String(it.detail || "").trim() || undefined, qty: Number(it.qty) || 0, rate: Number(it.rate) || 0 }));
    const row = { kind: d.kind, status: "draft", client_id: d.client_id || null, project_id: d.project_id || null, client: d.client || {}, items, currency: d.currency || "MYR", tax_rate: Number(d.tax_rate) || 0,
      discount: Number(d.discount) || 0, subtotal: totals.subtotal, tax: totals.tax, total: totals.total, issue_date: d.issue_date || today, due_date: d.kind === "receipt" ? null : (d.due_date || null),
      terms: d.terms || "", notes: d.notes || "", reference: d.reference || "", lang: d.lang || cfg.lang, payment: d.payment || {}, parent_id: d.parent_id || null };
    if (issue) {
      const problems = validateDoc({ ...row, items }, lang);
      if (problems.length) throw new Error(problems.join(" "));
    }
    let id = d.id;
    if (id) await patchDoc(id, row);
    else {
      const { data, error } = await supabase.from(TABLES.billingDocs).insert({ ...row, created_by: user?.id || null }).select("*");
      if (error) throw new Error(errText(error));
      id = data[0].id;
    }
    if (d.saveClient && row.client?.name) await upsertClient(row.client, d.client_id);
    if (!issue) { onToast(t("Draf disimpan.", "Draft saved."), "ok"); setEditing(null); return; }
    const { data: number, error } = await supabase.rpc("semasa_billing_issue", { p_id: id });
    if (error) throw new Error(errText(error));
    const fresh = (await supabase.from(TABLES.billingDocs).select("*").eq("id", id)).data?.[0];
    setEditing(null);
    onToast(t("{n} dikeluarkan.", "{n} issued.", { n: number }), "ok");
    if (send || cfg.email.auto_send) {
      if (fresh && validEmail(emailOf(fresh, clients.find((c) => c.id === fresh.client_id)))) {
        await enqueue(fresh, "send");
        onToast(t("E-mel dalam giliran: pekerja menghantarnya dalam seminit dua.", "E-mail queued: the worker sends it within a minute or two."), "ok");
      } else if (send) onToast(t("Dikeluarkan, tetapi tiada e-mel pelanggan: tambah alamat dahulu.", "Issued, but the client has no e-mail: add the address first."), "warn");
    }
    if (fresh) setViewing(fresh);
  });

  async function upsertClient(c, id) {
    const row = { name: c.name, reg_no: c.reg_no || "", attention: c.attention || "", email: c.email || "", phone: c.phone || "", address: c.address || "",
      postcode: c.postcode || "", city: c.city || "", state: c.state || "", country: c.country || "Malaysia", lang: c.lang === "bm" ? "bm" : "en", notes: c.notes || "" };
    const q = id ? supabase.from(TABLES.clients).update(row).eq("id", id) : supabase.from(TABLES.clients).insert({ ...row, created_by: user?.id || null });
    const { error } = await q;
    if (error) throw new Error(errText(error));
    clientsT.reload();
  }

  const act = guard(async (action, r) => {
    const d = docs.find((x) => x.id === r.id);
    if (!d) return;
    const st = effectiveStatus(d, today);
    switch (action) {
      case "view": setViewing(d); return;
      case "edit": if (d.status !== "draft") return setViewing(d); setEditing({ ...d, items: d.items?.length ? d.items : [{ description: "", qty: 1, rate: "" }] }); return;
      case "download": return download(d);
      case "link": await navigator.clipboard.writeText(publicLink(d.token, site)); onToast(t("Pautan disalin.", "Link copied."), "ok"); return;
      case "send": setSending({ doc: d, action: "send" }); return;
      case "reminder": setSending({ doc: d, action: "reminder" }); return;
      case "paid": setPaying({ docs: [d] }); return;
      case "convert": {
        const draft = invoiceFromQuotation(d, cfg, today);
        const { data, error } = await supabase.from(TABLES.billingDocs).insert({ ...draft, created_by: user?.id || null }).select("*");
        if (error) throw new Error(errText(error));
        if (OPEN.includes(d.status) || d.status === "accepted") { await patchDoc(d.id, { status: "converted" }); await logEvent(d.id, "converted", { invoice_id: data[0].id }); }
        setEditing({ ...data[0] });
        onToast(t("Invois draf dibuat daripada {n}.", "Draft invoice made from {n}.", { n: d.number }), "ok");
        return;
      }
      case "accepted": case "declined":
        await patchDoc(d.id, { status: action }); await logEvent(d.id, action, {}); return;
      case "void":
        if (!window.confirm(t("Batalkan {n}? Nombornya kekal dan kertas ini ditanda DIBATALKAN. Buat dokumen baharu untuk pembetulan.",
          "Void {n}? Its number stays and the paper is marked VOID. Make a new document for the correction.", { n: d.number }))) return;
        await patchDoc(d.id, { status: "void" }); await logEvent(d.id, "void", { was: st }); return;
      case "delete":
        if (d.status !== "draft" || !window.confirm(t("Padam draf ini?", "Delete this draft?"))) return;
        { const { error } = await supabase.from(TABLES.billingDocs).delete().eq("id", d.id); if (error) throw new Error(errText(error)); }
        return;
      case "duplicate":
        newDraft(d.kind, { client_id: d.client_id, project_id: d.project_id, client: d.client, items: d.items, tax_rate: d.tax_rate, discount: d.discount, terms: d.terms, notes: d.notes, reference: "", lang: d.lang });
        return;
      default:
    }
  });

  const bulk = guard(async (action, list) => {
    const ds = list.map((r) => docs.find((x) => x.id === r.id)).filter(Boolean);
    if (action === "download") return printHtml(pagesHtml(ds.map((d) => ({ ...d, project: projectName(d.project_id) })), cfg, (d) => ({ logoUrl: abs(`${base}logo-ink.png`), fontsCss: abs(`${base}fonts.css`), qr: d.token ? qrDataUrl(publicLink(d.token, site)) : "" })));
    if (action === "paid") return setPaying({ docs: ds });
    if (action === "reminder") {
      let n = 0;
      for (const d of ds) { try { await enqueue(d, "reminder", { meta: { manual: true } }); n++; } catch (e) { onToast(`${d.number}: ${e.message}`, "warn"); } }
      onToast(t("{n} peringatan dalam giliran.", "{n} reminders queued.", { n }), "ok");
    }
  });

  function download(d) {
    if (d.pdf_url && d.pdf_at && d.pdf_at >= (d.updated_at || "")) { window.open(d.pdf_url, "_blank", "noopener"); return; }
    printHtml(htmlOf(d));
  }
  function printHtml(html) {
    if (!html) return;
    setPrinting(html);
  }

  const sendNow = guard(async ({ doc, action, to, cc, subject, body }) => {
    await enqueue(doc, action, { to, cc: cc.split(/[,;\s]+/).map((s) => s.trim()).filter(validEmail), subject, body, meta: action === "reminder" ? { manual: true } : {} });
    setSending(null);
    onToast(t("Dalam giliran: pekerja menghantarnya dalam seminit dua, dan keputusannya muncul dalam garis masa dokumen.",
      "Queued: the worker sends it within a minute or two, and the outcome appears in the document's timeline."), "ok");
  });

  const markPaid = guard(async ({ docs: ds, method, date, reference, sendReceipt }) => {
    for (const inv of ds) {
      const payment = { method, date, reference };
      await patchDoc(inv.id, { status: "paid", paid_at: new Date(`${date}T12:00:00+08:00`).toISOString(), payment });
      await logEvent(inv.id, "paid", payment);
      const draft = receiptFromInvoice(inv, payment, cfg, today);
      const { data, error } = await supabase.from(TABLES.billingDocs).insert({ ...draft, created_by: user?.id || null }).select("*");
      if (error) throw new Error(errText(error));
      const { data: number, error: e2 } = await supabase.rpc("semasa_billing_issue", { p_id: data[0].id });
      if (e2) throw new Error(errText(e2));
      if (sendReceipt) {
        const fresh = (await supabase.from(TABLES.billingDocs).select("*").eq("id", data[0].id)).data?.[0];
        try { if (fresh) await enqueue(fresh, "send"); } catch (e) { onToast(`${number}: ${e.message}`, "warn"); }
      }
      onToast(t("{i} dibayar · resit {r} dikeluarkan.", "{i} paid · receipt {r} issued.", { i: inv.number, r: number }), "ok");
    }
    setPaying(null);
  });

  // ---- render ----------------------------------------------------------------------------------------------------------------
  if (notSetUp || !ready) {
    return (
      <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
        <Card className="flex items-start gap-3 p-5">
          <AlertTriangle className="mt-0.5 shrink-0 text-warn" size={18} />
          <div className="text-sm">
            <div className="font-medium">{t("Bil belum disediakan", "Billing is not set up yet")}</div>
            <p className="mt-1 text-muted">{t("Jalankan supabase/028_billing.sql sekali dalam Supabase SQL editor (projek KPI), kemudian muat semula halaman ini. Ia membuat jadual pelanggan, dokumen, acara, giliran e-mel dan pembilang nombor.",
              "Run supabase/028_billing.sql once in the Supabase SQL editor (the KPI project), then reload this page. It creates the client, document, event, e-mail queue and number counter tables.")}</p>
            {(docsT.error || clientsT.error) && <p className="mt-2 text-xs text-danger">{docsT.error || clientsT.error}</p>}
          </div>
        </Card>
      </main>
    );
  }

  const pendingMail = outboxT.rows.filter((o) => ["pending", "working"].includes(o.status)).length;
  const failedMail = outboxT.rows.filter((o) => o.status === "error").length;

  return (
    <main className="mx-auto max-w-page space-y-6 px-4 pb-20 pt-8 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl">{t("Bil & Resit", "Billing")}</h1>
          <p className="mt-1 text-sm text-muted">{t("Sebut harga → invois → resit. Nombor diberi oleh pangkalan data semasa dikeluarkan; e-mel dihantar oleh pekerja dari Gmail {e}.",
            "Quotation → invoice → receipt. Numbers are allocated by the database on issue; e-mail is sent by the worker from Gmail {e}.", { e: cfg.company.email || "" })}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => newDraft("quotation")}><Plus size={14} /> {t("Sebut harga", "Quotation")}</Button>
          <Button onClick={() => newDraft("invoice")}><Plus size={14} /> {t("Invois", "Invoice")}</Button>
          <Button variant="soft" onClick={() => newDraft("receipt")}><Plus size={14} /> {t("Resit", "Receipt")}</Button>
          <Button variant="ghost" onClick={() => setClientsOpen(true)}><Users size={14} /> {t("Pelanggan", "Clients")} ({clients.length})</Button>
          <Button variant="ghost" onClick={() => setProjectsOpen(true)}><Briefcase size={14} /> {t("Projek", "Projects")} ({projects.length})</Button>
          <Button variant="ghost" onClick={() => setSettingsOpen(true)}><Settings2 size={14} /> {t("Tetapan", "Settings")}</Button>
        </div>
      </motion.div>

      {/* the dashboard (components/ui/app-1.tsx, fed from the live documents) */}
      <App1
        stats={[
          { label: t("Belum dijelaskan", "Outstanding"), value: money(sum.outstanding, { currency: "MYR" }), hint: t("{n} invois", "{n} invoices", { n: sum.outstandingCount }), icon: Wallet },
          { label: t("Lewat", "Overdue"), value: money(sum.overdue, { currency: "MYR" }), hint: t("{n} invois", "{n} invoices", { n: sum.overdueCount }), icon: AlertTriangle, tone: sum.overdueCount ? "danger" : "" },
          { label: t("Dibayar bulan ini", "Paid this month"), value: money(sum.paidMonth, { currency: "MYR" }), hint: t("{n} invois", "{n} invoices", { n: sum.paidMonthCount }), icon: Check, tone: "ok" },
          { label: t("Sebut harga terbuka", "Open quotations"), value: money(sum.openQuotes, { currency: "MYR" }), icon: FileText,
            hint: sum.winRate == null ? t("{n} terbuka", "{n} open", { n: sum.openQuotesCount }) : t("{n} terbuka · {w}% diterima", "{n} open · {w}% won", { n: sum.openQuotesCount, w: sum.winRate }) },
        ]}
        series={weekly}
        formatValue={(n) => money(n, { currency: "MYR" })}
        projects={overviewProjects}
        activity={overviewActivity}
        words={{
          chartTitle: t("Diinvois lawan dibayar", "Invoiced against paid"), chartDescription: t("Lapan minggu terakhir, mengikut minggu invois dikeluarkan dan hari ia dibayar", "The last eight weeks, by the week an invoice was issued and the day it was paid"),
          invoiced: t("Diinvois", "Invoiced"), paid: t("Dibayar", "Paid"),
          projectsTitle: t("Projek aktif", "Active projects"), projectsDescription: t("Sejauh mana setiap projek sudah dibayar", "How far each project is paid"),
          noProjects: t("Tiada projek aktif. Tambah dalam Projek.", "No active projects. Add one under Projects."), due: t("Tamat", "Due"),
          activityTitle: t("Aktiviti terkini", "Recent activity"), activityDescription: pendingMail || failedMail
            ? [pendingMail ? t("{n} e-mel menunggu pekerja", "{n} e-mails waiting for the worker", { n: pendingMail }) : "", failedMail ? t("{n} e-mel gagal", "{n} e-mails failed", { n: failedMail }) : ""].filter(Boolean).join(" · ")
            : t("Apa yang berlaku pada setiap kertas", "What happened to each paper"),
          noActivity: t("Belum ada aktiviti.", "Nothing yet."),
        }}
        aside={
          <Card className="p-5">
            <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-medium">{t("Umur hutang", "Aging")}</h2><span className="text-xs text-muted">{t("invois belum dijelaskan, mengikut hari lewat", "unpaid invoices, by days past due")}</span></div>
            <Aging aging={sum.aging} total={sum.outstanding} t={t} />
          </Card>
        }
      />

      <Segmented value={kind} onChange={setKind} options={[["all", t("Semua", "All")], ...KINDS.map((k) => [k, kindLabel(k, lang)])]} />
      <DocumentsTable rows={rows} words={words} onAction={act} onBulk={bulk}
        emptyHint={docs.length ? undefined : t("Belum ada dokumen. Mulakan dengan + Sebut harga atau + Invois.", "No documents yet. Start with + Quotation or + Invoice.")} />

      {editing && <Editor doc={editing} clients={clients} projects={projects} counters={countersT.rows} cfg={cfg} onChange={setEditing} onClose={() => setEditing(null)}
        onSave={(opts) => saveDraft(editing, opts)} busy={!!busy} t={t} lang={lang} today={today} />}
      {viewing && <Viewer doc={docs.find((x) => x.id === viewing.id) || viewing} html={htmlOf(docs.find((x) => x.id === viewing.id) || viewing)} events={eventsT.rows.filter((e) => e.doc_id === viewing.id)}
        outbox={outboxT.rows.filter((o) => o.doc_id === viewing.id)} onClose={() => setViewing(null)} onAction={(a) => act(a, { id: viewing.id })} onRetry={guard(async (o) => {
          await enqueue(docs.find((x) => x.id === o.doc_id), o.action, { to: o.to_email, cc: o.cc || [], subject: o.subject, body: o.body, meta: o.meta || {} });
        })} t={t} lang={lang} today={today} site={site} />}
      {sending && <SendModal doc={sending.doc} action={sending.action} cfg={cfg} clients={clients} site={site} onClose={() => setSending(null)} onSend={sendNow} busy={!!busy} t={t} />}
      {paying && <PayModal docs={paying.docs} lang={lang} onClose={() => setPaying(null)} onPay={markPaid} busy={!!busy} t={t} today={today} />}
      {clientsOpen && <ClientsModal clients={clients} docs={docs} defaultLang={cfg.lang} onClose={() => setClientsOpen(false)} onSave={guard(upsertClient)} onDelete={guard(async (c) => {
        if (!window.confirm(t("Padam {n}? Dokumen yang sudah dikeluarkan kekal (butirannya disalin pada kertas).", "Delete {n}? Issued documents keep their copy of the details.", { n: c.name }))) return;
        const { error } = await supabase.from(TABLES.clients).delete().eq("id", c.id); if (error) throw new Error(errText(error)); clientsT.reload();
      })} t={t} lang={lang} />}
      {projectsOpen && <ProjectsModal projects={projects} clients={clients} docs={docs} today={today} onClose={() => setProjectsOpen(false)} t={t} lang={lang}
        onNewDoc={(k, p) => { setProjectsOpen(false); newDraft(k, { client_id: p.client_id, project_id: p.id, reference: p.reference || "" }); }}
        onOpenDoc={(d) => { setProjectsOpen(false); setViewing(d); }}
        onSave={guard(async (p) => {
          const row = { client_id: p.client_id, name: p.name.trim(), details: p.details || "", status: p.status || "active", start_date: p.start_date || null,
            end_date: p.end_date || null, budget: p.budget === "" || p.budget == null ? null : Number(p.budget), reference: p.reference || "", notes: p.notes || "" };
          const q = p.id ? supabase.from(TABLES.projects).update(row).eq("id", p.id) : supabase.from(TABLES.projects).insert({ ...row, created_by: user?.id || null });
          const { error } = await q; if (error) throw new Error(errText(error)); projectsT.reload();
        })}
        onDelete={guard(async (p) => {
          if (!window.confirm(t("Padam projek {n}? Dokumennya kekal, tanpa projek.", "Delete project {n}? Its documents stay, without a project.", { n: p.name }))) return;
          const { error } = await supabase.from(TABLES.projects).delete().eq("id", p.id); if (error) throw new Error(errText(error)); projectsT.reload();
        })} />}
      {settingsOpen && <SettingsModal cfg={cfg} counters={countersT.rows} onClose={() => setSettingsOpen(false)} busy={!!busy} t={t}
        onSave={guard(async (v, counters) => {
          await save("billing", v);
          for (const c of counters || []) {
            const { error } = await supabase.from(TABLES.billingCounters).upsert({ prefix: c.prefix, year: Number(c.year), last: Number(c.last) || 0 }, { onConflict: "prefix,year" });
            if (error) throw new Error(errText(error));
          }
          onToast(t("Tetapan disimpan.", "Settings saved."), "ok"); setSettingsOpen(false);
        })} />}
      {printing && <PrintFrame html={printing} onDone={() => setPrinting("")} />}
    </main>
  );
}

function eventLabel(ev, t) {
  const d = ev.detail || {};
  switch (ev.kind) {
    case "issued": return t("dikeluarkan", "issued");
    case "send": return t("e-mel dihantar ke {to}", "e-mailed to {to}", { to: d.to || "" });
    case "reminder": return t("peringatan dihantar ke {to}", "reminder sent to {to}", { to: d.to || "" });
    case "viewed": return t("dibuka oleh pelanggan", "opened by the client");
    case "paid": return t("dibayar ({m})", "paid ({m})", { m: d.method || "" });
    case "converted": return t("dijadikan invois", "converted to an invoice");
    case "void": return t("dibatalkan", "voided");
    case "expired": return t("luput", "expired");
    case "accepted": return t("diterima", "accepted");
    case "declined": return t("ditolak", "declined");
    case "pdf": return t("PDF dilukis", "PDF rendered");
    case "email_failed": return t("e-mel gagal: {e}", "e-mail failed: {e}", { e: d.error || "" });
    default: return ev.kind;
  }
}

function Aging({ aging, total, t }) {
  const buckets = [["current", t("belum tiba", "not yet due"), "bg-accent"], ["d30", "1–30", "bg-warn/70"], ["d60", "31–60", "bg-warn"], ["d90", "61–90", "bg-danger/70"], ["older", "90+", "bg-danger"]];
  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-pill bg-surface-2">
        {total > 0 && buckets.map(([k, , cls]) => aging[k] > 0 && <div key={k} className={cls} style={{ width: `${(100 * aging[k]) / total}%` }} title={money(aging[k])} />)}
      </div>
      <div className="mt-2 grid grid-cols-5 gap-2 text-[11px]">
        {buckets.map(([k, label, cls]) => (
          <div key={k}><div className="flex items-center gap-1 text-muted"><span className={`inline-block h-2 w-2 rounded-full ${cls}`} />{label}</div><div className="font-medium tabular-nums">{money(aging[k])}</div></div>
        ))}
      </div>
    </div>
  );
}

/* A wide right-hand sheet (the Field Modal is a narrow centre box; a document wants room for a preview). */
function Sheet({ title, onClose, children, width = "max-w-5xl", actions }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-3 sm:p-6" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`w-full ${width} rounded-card border border-line bg-surface shadow-lift`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h3 className="text-lg">{title}</h3>
          <div className="flex items-center gap-2">{actions}<button type="button" onClick={onClose} className="rounded-tile p-1.5 text-muted hover:bg-surface-2 hover:text-ink" aria-label="Close"><X size={16} /></button></div>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

function ClientFields({ c, onChange, t, lang }) {
  const set = (k) => (e) => onChange({ ...c, [k]: e.target.value });
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block sm:col-span-2"><Label>{t("Nama syarikat / pelanggan", "Company / client name")}</Label><Input value={c.name || ""} onChange={set("name")} /></label>
      <label className="block"><Label>{t("No. pendaftaran (SSM)", "Registration no. (SSM)")}</Label><Input value={c.reg_no || ""} onChange={set("reg_no")} /></label>
      <label className="block"><Label>{t("Untuk perhatian", "Attention")}</Label><Input value={c.attention || ""} onChange={set("attention")} placeholder={t("Nama orang hubungan", "Contact person")} /></label>
      <label className="block"><Label>{t("E-mel", "E-mail")}</Label><Input type="email" value={c.email || ""} onChange={set("email")} /></label>
      <label className="block"><Label>{t("Telefon", "Phone")}</Label><Input value={c.phone || ""} onChange={set("phone")} /></label>
      <label className="block sm:col-span-2"><Label>{t("Alamat", "Address")}</Label><TextArea rows={2} value={c.address || ""} onChange={set("address")} /></label>
      <label className="block"><Label>{t("Poskod", "Postcode")}</Label><Input value={c.postcode || ""} onChange={set("postcode")} /></label>
      <label className="block"><Label>{t("Bandar", "City")}</Label><Input value={c.city || ""} onChange={set("city")} /></label>
      <label className="block"><Label>{t("Negeri", "State")}</Label>
        <Select value={c.state || ""} onChange={(v) => onChange({ ...c, state: v })} options={[["", "—"], ...STATES.map((s) => [s, s])]} className="w-full" /></label>
      <label className="block"><Label>{t("Negara", "Country")}</Label><Input value={c.country || "Malaysia"} onChange={set("country")} /></label>
      {"lang" in c && <label className="block"><Label>{t("Bahasa dokumen", "Document language")}</Label>
        <Select value={c.lang || "en"} onChange={(v) => onChange({ ...c, lang: v })} options={[["en", "English"], ["bm", "Bahasa Malaysia"]]} className="w-full" /></label>}
    </div>
  );
}

function Editor({ doc, clients, projects, counters, cfg, onChange, onClose, onSave, busy, t, lang, today }) {
  const d = doc;
  const totals = calcTotals(d.items, { tax_rate: d.tax_rate, discount: d.discount });
  const problems = validateDoc({ ...d, items: d.items.filter((it) => String(it.description || "").trim()) }, lang);
  const next = numberPreview(d.kind, counters, cfg, Number((d.issue_date || today).slice(0, 4)));
  const setItem = (i, k, v) => onChange({ ...d, items: d.items.map((it, j) => (j === i ? { ...it, [k]: v } : it)) });
  const pick = (id) => {
    const c = clients.find((x) => x.id === id);
    const keep = projects.some((p) => p.id === d.project_id && p.client_id === id);
    onChange({ ...d, client_id: id || null, client: c ? clientSnapshot(c) : d.client, lang: c?.lang || d.lang, project_id: keep ? d.project_id : null });
  };
  const myProjects = projects.filter((p) => p.client_id === d.client_id && !["cancelled"].includes(p.status));
  const email = emailOf(d, clients.find((c) => c.id === d.client_id));
  const title = `${d.id ? t("Sunting draf", "Edit draft") : t("Baharu", "New")}: ${kindLabel(d.kind, lang)} · ${t("seterusnya", "next")} ${next}`;
  return (
    <Sheet title={title} onClose={onClose} actions={
      <>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => onSave({})}>{t("Simpan draf", "Save draft")}</Button>
        <Button size="sm" disabled={busy || problems.length > 0} title={problems.join("\n")} onClick={() => onSave({ issue: true })}>
          <FileText size={14} /> {t("Keluarkan {n}", "Issue {n}", { n: next })}
        </Button>
        <Button size="sm" disabled={busy || problems.length > 0 || !validEmail(email)} title={!validEmail(email) ? t("Tiada e-mel pelanggan", "No client e-mail") : ""} onClick={() => onSave({ issue: true, send: true })}>
          <Send size={14} /> {t("Keluarkan & e-mel", "Issue & e-mail")}
        </Button>
      </>}>
      <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block"><Label>{t("Tarikh keluar", "Issue date")}</Label><Input type="date" value={d.issue_date || ""} onChange={(e) => onChange({ ...d, issue_date: e.target.value })} /></label>
            {d.kind !== "receipt" && <label className="block"><Label>{d.kind === "quotation" ? t("Sah sehingga", "Valid until") : t("Tarikh akhir bayaran", "Payment due")}</Label>
              <Input type="date" value={d.due_date || ""} onChange={(e) => onChange({ ...d, due_date: e.target.value })} /></label>}
            {d.kind === "receipt" && <label className="block"><Label>{t("Tarikh bayaran", "Payment date")}</Label>
              <Input type="date" value={d.payment?.date || ""} onChange={(e) => onChange({ ...d, payment: { ...(d.payment || {}), date: e.target.value } })} /></label>}
            <label className="block"><Label>{d.kind === "receipt" ? t("Untuk invois / rujukan", "For invoice / reference") : t("Rujukan pelanggan (PO)", "Client reference (PO)")}</Label>
              <Input value={d.reference || ""} onChange={(e) => onChange({ ...d, reference: e.target.value })} /></label>
          </div>
          {d.kind === "receipt" && (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block"><Label>{t("Kaedah bayaran", "Payment method")}</Label>
                <Select value={d.payment?.method || ""} onChange={(v) => onChange({ ...d, payment: { ...(d.payment || {}), method: v } })} options={METHODS[lang].map((m) => [m, m])} className="w-full" /></label>
              <label className="block"><Label>{t("Rujukan bayaran", "Payment reference")}</Label>
                <Input value={d.payment?.reference || ""} onChange={(e) => onChange({ ...d, payment: { ...(d.payment || {}), reference: e.target.value } })} /></label>
            </div>
          )}
          <div className="rounded-tile border border-line p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <Label>{t("Pelanggan", "Client")}</Label>
              <Select value={d.client_id || ""} onChange={pick} options={[["", t("— pilih daripada senarai —", "— pick from the list —")], ...clients.map((c) => [c.id, c.name])]} />
            </div>
            {d.client_id && (
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <Label>{t("Projek", "Project")}</Label>
                <Select value={d.project_id || ""} onChange={(v) => onChange({ ...d, project_id: v || null, reference: d.reference || projects.find((p) => p.id === v)?.reference || "" })}
                  options={[["", t("— tiada projek —", "— no project —")], ...myProjects.map((p) => [p.id, p.name])]} />
                {!myProjects.length && <span className="text-xs text-muted">{t("Pelanggan ini belum ada projek: tambah dalam Projek.", "This client has no project yet: add one under Projects.")}</span>}
              </div>
            )}
            <ClientFields c={d.client || {}} onChange={(c) => onChange({ ...d, client: c })} t={t} lang={lang} />
            <label className="mt-2 flex items-center gap-2 text-xs text-muted">
              <input type="checkbox" checked={!!d.saveClient} onChange={(e) => onChange({ ...d, saveClient: e.target.checked })} />
              {d.client_id ? t("Kemas kini rekod pelanggan dengan butiran ini", "Update the client record with these details") : t("Simpan sebagai pelanggan baharu", "Save as a new client")}
            </label>
          </div>
          <div>
            <div className="mb-1 flex items-center justify-between"><Label>{t("Perkhidmatan", "Services")}</Label>
              <Label>{t("Bahasa", "Language")}: <select className="ml-1 rounded-pill border border-line bg-surface px-2 py-0.5 text-xs" value={d.lang || "en"} onChange={(e) => onChange({ ...d, lang: e.target.value })}><option value="en">EN</option><option value="bm">BM</option></select></Label></div>
            <div className="space-y-2">
              {d.items.map((it, i) => (
                <div key={i} className="grid grid-cols-[1fr_64px_96px_28px] items-start gap-2">
                  <div>
                    <Input value={it.description || ""} onChange={(e) => setItem(i, "description", e.target.value)} placeholder={t("Keterangan perkhidmatan", "Description of service")} />
                    <input className="mt-1 w-full rounded-pill border border-line/60 bg-bg px-3 py-1 text-xs outline-none focus:border-accent" value={it.detail || ""}
                      onChange={(e) => setItem(i, "detail", e.target.value)} placeholder={t("Butiran kecil (pilihan)", "Small print (optional)")} />
                  </div>
                  <Input type="number" min="0" step="1" value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} aria-label="qty" />
                  <Input type="number" min="0" step="0.01" value={it.rate} onChange={(e) => setItem(i, "rate", e.target.value)} placeholder="0.00" aria-label="rate" />
                  <button type="button" className="mt-2 text-muted hover:text-danger" onClick={() => onChange({ ...d, items: d.items.filter((_, j) => j !== i) })} aria-label={t("Buang baris", "Remove line")}><Trash2 size={14} /></button>
                </div>
              ))}
            </div>
            <Button variant="ghost" size="sm" className="mt-2" onClick={() => onChange({ ...d, items: [...d.items, { description: "", qty: 1, rate: "" }] })}><Plus size={14} /> {t("Baris", "Line")}</Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block"><Label>{t("Diskaun (MYR)", "Discount (MYR)")}</Label><Input type="number" min="0" step="0.01" value={d.discount || ""} onChange={(e) => onChange({ ...d, discount: e.target.value })} /></label>
            <label className="block"><Label>{t("Cukai %", "Tax %")}</Label><Input type="number" min="0" step="0.01" value={d.tax_rate ?? 0} onChange={(e) => onChange({ ...d, tax_rate: e.target.value })} /></label>
            <div className="rounded-tile bg-surface-2 p-3 text-right"><div className="text-[11px] uppercase tracking-widest text-muted">{t("Jumlah", "Total")}</div><div className="font-display text-xl tabular-nums">{money(totals.total, { currency: d.currency || "MYR" })}</div></div>
          </div>
          <label className="block"><Label>{t("Terma & syarat", "Terms & conditions")}</Label><TextArea rows={4} value={d.terms || ""} onChange={(e) => onChange({ ...d, terms: e.target.value })} /></label>
          <label className="block"><Label>{t("Nota (dicetak)", "Notes (printed)")}</Label><TextArea rows={2} value={d.notes || ""} onChange={(e) => onChange({ ...d, notes: e.target.value })} /></label>
          {problems.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-xs text-warn">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
        </div>
        <div className="hidden lg:block">
          <Label>{t("Pratonton (kertas A4 sebenar)", "Preview (the real A4 paper)")}</Label>
          <Preview html={documentHtml({ ...d, status: "draft", number: "" }, cfg, { logoUrl: new URL(`${import.meta.env.BASE_URL}cards/logo-ink.png`, window.location.href).href,
            fontsCss: new URL(`${import.meta.env.BASE_URL}cards/fonts.css`, window.location.href).href })} />
        </div>
      </div>
    </Sheet>
  );
}

function Preview({ html, tall }) {
  return <iframe title="preview" srcDoc={html} className={`w-full rounded-tile border border-line bg-[#e9eef2] ${tall ? "h-[80vh]" : "h-[72vh]"}`} />;
}

function Viewer({ doc: d, html, events, outbox, onClose, onAction, onRetry, t, lang, today, site }) {
  const st = effectiveStatus(d, today);
  const tone = st === "paid" ? "bg-ok/10 text-ok" : ["overdue", "expired", "void", "declined"].includes(st) ? "bg-danger/10 text-danger" : "bg-surface-2 text-ink";
  const reminder = nextReminder(d, DEFAULT_OFFSETS, today);
  return (
    <Sheet title={`${kindLabel(d.kind, lang)} ${d.number || ""}`} onClose={onClose} width="max-w-6xl" actions={
      <>
        <span className={`rounded-pill px-2 py-0.5 text-xs font-medium ${tone}`}>{statusLabel(st, lang)}</span>
        <Button variant="ghost" size="sm" onClick={() => onAction("download")}><Download size={14} /> PDF</Button>
        {d.status !== "void" && <Button variant="ghost" size="sm" onClick={() => onAction("link")}><Link2 size={14} /> {t("Pautan", "Link")}</Button>}
        {d.status === "draft" ? <Button size="sm" onClick={() => onAction("edit")}><Pencil size={14} /> {t("Sunting", "Edit")}</Button>
          : d.status !== "void" && <Button size="sm" onClick={() => onAction("send")}><Mail size={14} /> {t("E-mel", "E-mail")}</Button>}
      </>}>
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <Preview html={html} tall />
        <div className="space-y-4 text-sm">
          <div className="rounded-tile border border-line p-3">
            <div className="text-[11px] uppercase tracking-widest text-muted">{t("Jumlah", "Total")}</div>
            <div className="font-display text-2xl tabular-nums">{money(d.total, { currency: d.currency || "MYR" })}</div>
            <div className="mt-1 text-xs text-muted">{t("Dikeluarkan", "Issued")} {fmtDate(d.issue_date)}{d.due_date ? ` · ${d.kind === "quotation" ? t("sah sehingga", "valid until") : t("akhir", "due")} ${fmtDate(d.due_date)}` : ""}</div>
            {d.client?.email && <div className="mt-1 text-xs text-muted">{d.client.email}</div>}
            {d.kind === "invoice" && OPEN.includes(d.status) && <div className="mt-2 text-xs text-muted">{reminder != null
              ? t("Peringatan automatik seterusnya: hari {o} berbanding tarikh akhir (sedia dihantar).", "Next automatic reminder: day {o} relative to due (ready to send).", { o: reminder })
              : d.status === "issued" ? t("Belum dihantar: peringatan automatik bermula selepas e-mel pertama.", "Not sent yet: automatic reminders start after the first e-mail.") : ""}</div>}
          </div>
          <div className="flex flex-wrap gap-2">
            {d.kind === "invoice" && ["issued", "sent", "viewed", "overdue"].includes(st) && <>
              <Button size="sm" onClick={() => onAction("paid")}><Check size={14} /> {t("Tanda dibayar → resit", "Mark paid → receipt")}</Button>
              {st !== "issued" && <Button variant="soft" size="sm" onClick={() => onAction("reminder")}><Bell size={14} /> {t("Peringatan", "Reminder")}</Button>}
            </>}
            {d.kind === "quotation" && ["issued", "sent", "viewed", "accepted", "expired"].includes(st) && <Button size="sm" onClick={() => onAction("convert")}><Receipt size={14} /> {t("Jadikan invois", "Convert to invoice")}</Button>}
            {d.kind === "quotation" && ["issued", "sent", "viewed"].includes(st) && <>
              <Button variant="soft" size="sm" onClick={() => onAction("accepted")}>{t("Diterima", "Accepted")}</Button>
              <Button variant="ghost" size="sm" onClick={() => onAction("declined")}>{t("Ditolak", "Declined")}</Button></>}
            <Button variant="ghost" size="sm" onClick={() => onAction("duplicate")}><Copy size={14} /> {t("Salin", "Duplicate")}</Button>
            {d.kind === "invoice" && ["issued", "sent", "viewed", "overdue"].includes(st) && <Button variant="danger" size="sm" onClick={() => onAction("void")}>{t("Batalkan", "Void")}</Button>}
            {d.status === "draft" && <Button variant="danger" size="sm" onClick={() => onAction("delete")}><Trash2 size={14} /> {t("Padam", "Delete")}</Button>}
          </div>
          {outbox.length > 0 && (
            <div>
              <Label>{t("E-mel", "E-mails")}</Label>
              <ul className="space-y-1 text-xs">
                {outbox.map((o) => (
                  <li key={o.id} className="rounded-tile border border-line/70 p-2">
                    <div className="flex items-center justify-between gap-2">
                      <span>{o.action === "reminder" ? t("Peringatan", "Reminder") : t("Hantar", "Send")} → {o.to_email}</span>
                      <span className={o.status === "sent" ? "text-ok" : o.status === "error" ? "text-danger" : "text-warn"}>{o.status === "pending" ? t("menunggu pekerja", "waiting for the worker") : o.status === "working" ? t("sedang dihantar", "sending") : o.status === "sent" ? t("dihantar", "sent") : t("gagal", "failed")}</span>
                    </div>
                    <div className="text-muted">{stampMYT(o.updated_at || o.created_at)}</div>
                    {o.error && <div className="mt-1 text-danger">{o.error}</div>}
                    {o.status === "error" && <Button variant="ghost" size="sm" className="mt-1" onClick={() => onRetry(o)}>{t("Cuba lagi", "Try again")}</Button>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <Label>{t("Garis masa", "Timeline")}</Label>
            <DocHistory doc={d} events={events} t={t} />
          </div>
          {d.token && d.status !== "draft" && <div className="break-all text-[11px] text-muted"><Eye size={11} className="mr-1 inline" />{publicLink(d.token, site)}</div>}
        </div>
      </div>
    </Sheet>
  );
}

function SendModal({ doc, action, cfg, clients, site, onClose, onSend, busy, t }) {
  const client = clients.find((c) => c.id === doc.client_id);
  const draft = useMemo(() => emailFor({ doc, action, settings: cfg, link: publicLink(doc.token, site) }), [doc, action, cfg, site]);
  const [to, setTo] = useState(emailOf(doc, client));
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.text);
  return (
    <Sheet title={action === "reminder" ? t("Hantar peringatan: {n}", "Send reminder: {n}", { n: doc.number }) : t("E-mel {k} {n}", "E-mail {k} {n}", { k: kindLabel(doc.kind), n: doc.number })} onClose={onClose} width="max-w-2xl"
      actions={<Button size="sm" disabled={busy || !validEmail(to)} onClick={() => onSend({ doc, action, to, cc, subject, body })}><Send size={14} /> {t("Hantar", "Send")}</Button>}>
      <div className="space-y-3">
        <label className="block"><Label>{t("Kepada", "To")}</Label><Input type="email" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label className="block"><Label>{t("Sk (dipisahkan koma)", "Cc (comma-separated)")}{cfg.email.cc_self && cfg.company.email ? ` · ${t("salinan ke", "copy to")} ${cfg.company.email}` : ""}</Label><Input value={cc} onChange={(e) => setCc(e.target.value)} /></label>
        <label className="block"><Label>{t("Tajuk", "Subject")}</Label><Input value={subject} onChange={(e) => setSubject(e.target.value)} /></label>
        <label className="block"><Label>{t("Mesej", "Message")}</Label><TextArea rows={9} value={body} onChange={(e) => setBody(e.target.value)} /></label>
        <p className="text-xs text-muted"><Printer size={12} className="mr-1 inline" />{t("Lampiran: {f} (dilukis oleh pekerja semasa menghantar). Dihantar dari {e}.", "Attachment: {f} (rendered by the worker when it sends). Sent from {e}.", { f: fileName(doc), e: cfg.company.email || "Gmail" })}</p>
      </div>
    </Sheet>
  );
}

function PayModal({ docs, lang, onClose, onPay, busy, t, today }) {
  const [method, setMethod] = useState(METHODS[lang][0]);
  const [date, setDate] = useState(today);
  const [reference, setReference] = useState("");
  const [sendReceipt, setSendReceipt] = useState(true);
  const total = docs.reduce((s, d) => s + (Number(d.total) || 0), 0);
  return (
    <Sheet title={t("Tanda dibayar: {n}", "Mark as paid: {n}", { n: docs.map((d) => d.number).join(", ") })} onClose={onClose} width="max-w-lg"
      actions={<Button size="sm" disabled={busy || !date} onClick={() => onPay({ docs, method, date, reference, sendReceipt })}><Check size={14} /> {t("Bayar & keluarkan resit", "Paid & issue receipt")}</Button>}>
      <div className="space-y-3">
        <div className="rounded-tile bg-surface-2 p-3 text-sm">{t("Jumlah", "Total")}: <b className="tabular-nums">{money(total, { currency: "MYR" })}</b> · {t("{n} invois", "{n} invoices", { n: docs.length })}</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><Label>{t("Tarikh bayaran", "Payment date")}</Label><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
          <label className="block"><Label>{t("Kaedah", "Method")}</Label><Select value={method} onChange={setMethod} options={METHODS[lang].map((m) => [m, m])} className="w-full" /></label>
        </div>
        <label className="block"><Label>{t("Rujukan bayaran (pilihan)", "Payment reference (optional)")}</Label><Input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="DuitNow / cek / slip" /></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sendReceipt} onChange={(e) => setSendReceipt(e.target.checked)} />{t("E-mel resit kepada pelanggan", "E-mail the receipt to the client")}</label>
        <p className="text-xs text-muted">{t("Setiap invois mendapat resit bernombor sendiri (RPT-…), dengan baris dan jumlah yang sama.", "Each invoice gets its own numbered receipt (RPT-…), with the same lines and total.")}</p>
      </div>
    </Sheet>
  );
}

function ClientsModal({ clients, docs, onClose, onSave, onDelete, t, lang, defaultLang = "en" }) {
  const [editing, setEditing] = useState(null);
  const [q, setQ] = useState("");
  const list = clients.filter((c) => !q || `${c.name} ${c.email} ${c.reg_no}`.toLowerCase().includes(q.toLowerCase()));
  const countOf = (id) => docs.filter((d) => d.client_id === id).length;
  return (
    <Sheet title={t("Pelanggan", "Clients")} onClose={onClose} width="max-w-4xl" actions={<Button size="sm" onClick={() => setEditing({ ...BLANK_CLIENT, lang: defaultLang })}><Plus size={14} /> {t("Pelanggan", "Client")}</Button>}>
      {editing ? (
        <div className="space-y-3">
          <ClientFields c={editing} onChange={setEditing} t={t} lang={lang} />
          <label className="block"><Label>{t("Nota dalaman", "Internal notes")}</Label><TextArea rows={2} value={editing.notes || ""} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} /></label>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>{t("Batal", "Cancel")}</Button>
            <Button disabled={!editing.name?.trim()} onClick={async () => { await onSave(editing, editing.id); setEditing(null); }}>{t("Simpan", "Save")}</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari pelanggan…", "Search clients…")} />
          <ul className="divide-y divide-line/70 text-sm">
            {list.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="font-medium">{c.name} <span className="text-xs text-muted">{c.reg_no}</span></div>
                  <div className="truncate text-xs text-muted">{[c.attention, c.email, c.phone, c.city, c.state].filter(Boolean).join(" · ")}</div>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-xs text-muted">
                  <Building2 size={12} /> {countOf(c.id)}
                  <Button variant="ghost" size="sm" onClick={() => setEditing({ ...BLANK_CLIENT, ...c })}><Pencil size={12} /></Button>
                  <Button variant="ghost" size="sm" onClick={() => onDelete(c)}><Trash2 size={12} /></Button>
                </div>
              </li>
            ))}
            {!list.length && <li className="py-6 text-center text-muted">{t("Tiada pelanggan lagi.", "No clients yet.")}</li>}
          </ul>
        </div>
      )}
    </Sheet>
  );
}

const BLANK_PROJECT = { client_id: "", name: "", details: "", status: "active", start_date: "", end_date: "", budget: "", reference: "", notes: "" };

/* Client → Project → details (Wan, 7 Oct 2026). A project is a client's piece of work; its documents hang off it, so its money
   reads in one place. The timeline draws every project with dates by month (a small strip of our own, see ops/BILLING.md). */
function ProjectsModal({ projects, clients, docs, today, onClose, onSave, onDelete, onNewDoc, onOpenDoc, t, lang }) {
  const [editing, setEditing] = useState(null);
  const [clientId, setClientId] = useState("");
  const [open, setOpen] = useState("");
  const list = projects.filter((p) => !clientId || p.client_id === clientId);
  const clientName = (id) => clients.find((c) => c.id === id)?.name || "—";
  const L = lang === "en" ? "en" : "bm";
  const statusTone = { lead: "bg-surface-2 text-muted", active: "bg-accent/10 text-accent", on_hold: "bg-warn/10 text-warn", done: "bg-ok/10 text-ok", cancelled: "bg-danger/10 text-danger" };
  const set = (k) => (e) => setEditing({ ...editing, [k]: e.target.value });
  return (
    <Sheet title={t("Projek", "Projects")} onClose={onClose} width="max-w-5xl"
      actions={!editing && <Button size="sm" disabled={!clients.length} onClick={() => setEditing({ ...BLANK_PROJECT, client_id: clientId || clients[0]?.id || "" })}><Plus size={14} /> {t("Projek", "Project")}</Button>}>
      {editing ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block sm:col-span-2"><Label>{t("Pelanggan", "Client")}</Label>
              <Select value={editing.client_id} onChange={(v) => setEditing({ ...editing, client_id: v })} options={clients.map((c) => [c.id, c.name])} className="w-full" /></label>
            <label className="block sm:col-span-2"><Label>{t("Nama projek", "Project name")}</Label><Input value={editing.name} onChange={set("name")} placeholder={t("Cth: Notifikasi 3 produk skincare", "E.g. Notification of 3 skincare products")} /></label>
            <label className="block sm:col-span-2"><Label>{t("Butiran (skop, produk, apa yang dipersetujui)", "Details (scope, products, what was agreed)")}</Label><TextArea rows={4} value={editing.details} onChange={set("details")} /></label>
            <label className="block"><Label>{t("Status", "Status")}</Label>
              <Select value={editing.status} onChange={(v) => setEditing({ ...editing, status: v })} options={Object.entries(PROJECT_STATUS).map(([k, v]) => [k, v[L]])} className="w-full" /></label>
            <label className="block"><Label>{t("Yuran dipersetujui (MYR, pilihan)", "Agreed fee (MYR, optional)")}</Label><Input type="number" min="0" step="0.01" value={editing.budget ?? ""} onChange={set("budget")} /></label>
            <label className="block"><Label>{t("Mula", "Start")}</Label><Input type="date" value={editing.start_date || ""} onChange={set("start_date")} /></label>
            <label className="block"><Label>{t("Tamat", "End")}</Label><Input type="date" value={editing.end_date || ""} onChange={set("end_date")} /></label>
            <label className="block"><Label>{t("Rujukan pelanggan (PO / fail)", "Client reference (PO / file)")}</Label><Input value={editing.reference} onChange={set("reference")} /></label>
            <label className="block"><Label>{t("Nota dalaman", "Internal notes")}</Label><Input value={editing.notes} onChange={set("notes")} /></label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditing(null)}>{t("Batal", "Cancel")}</Button>
            <Button disabled={!editing.name.trim() || !editing.client_id || (editing.start_date && editing.end_date && editing.end_date < editing.start_date)}
              onClick={async () => { await onSave(editing); setEditing(null); }}>{t("Simpan", "Save")}</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Label>{t("Pelanggan", "Client")}</Label>
            <Select value={clientId} onChange={setClientId} options={[["", t("Semua", "All")], ...clients.map((c) => [c.id, c.name])]} />
            {!clients.length && <span className="text-xs text-muted">{t("Daftarkan pelanggan dahulu.", "Register a client first.")}</span>}
          </div>
          <ul className="divide-y divide-line/70">
            {list.map((p) => {
              const m = projectSummary(p.id, docs, today);
              const mine = docs.filter((d) => d.project_id === p.id).sort((a, b) => String(b.issue_date || b.created_at).localeCompare(String(a.issue_date || a.created_at)));
              return (
                <li key={p.id} className="py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <button type="button" className="min-w-0 text-left" onClick={() => setOpen(open === p.id ? "" : p.id)}>
                      <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{p.name}</span>
                        <span className={`rounded-pill px-2 py-0.5 text-[11px] ${statusTone[p.status] || ""}`}>{PROJECT_STATUS[p.status]?.[L] || p.status}</span>
                        <span className="text-xs text-muted">{clientName(p.client_id)}</span></div>
                      <div className="mt-0.5 text-xs text-muted">{[p.start_date && fmtDate(p.start_date), p.end_date && fmtDate(p.end_date)].filter(Boolean).join(" → ")}{p.reference ? ` · ${p.reference}` : ""}</div>
                    </button>
                    <div className="flex flex-wrap items-center gap-3 text-xs tabular-nums">
                      <span title={t("Disebut harga", "Quoted")}>{t("SH", "Q")} {money(m.quoted)}</span>
                      <span title={t("Diinvois", "Invoiced")}>{t("Inv", "Inv")} {money(m.invoiced)}</span>
                      <span className="text-ok" title={t("Dibayar", "Paid")}>{t("Bayar", "Paid")} {money(m.paid)}</span>
                      {m.outstanding > 0 && <span className={m.overdue > 0 ? "text-danger" : "text-warn"} title={t("Belum dijelaskan", "Outstanding")}>{t("Baki", "Due")} {money(m.outstanding)}</span>}
                      {p.budget != null && <span className="text-muted" title={t("Yuran dipersetujui", "Agreed fee")}>/ {money(p.budget)}</span>}
                      <Button variant="ghost" size="sm" onClick={() => setEditing({ ...BLANK_PROJECT, ...p, budget: p.budget ?? "" })}><Pencil size={12} /></Button>
                      <Button variant="ghost" size="sm" onClick={() => onDelete(p)}><Trash2 size={12} /></Button>
                    </div>
                  </div>
                  <div className="mt-3 overflow-x-auto"><ProjectStages project={p} docs={docs} today={today} t={t} lang={L} /></div>
                  {open === p.id && (
                    <div className="mt-2 rounded-tile bg-surface-2 p-3 text-sm">
                      {p.details && <p className="whitespace-pre-wrap text-ink">{p.details}</p>}
                      {p.notes && <p className="mt-1 text-xs text-muted">{p.notes}</p>}
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Button size="sm" onClick={() => onNewDoc("quotation", p)}><Plus size={12} /> {t("Sebut harga", "Quotation")}</Button>
                        <Button size="sm" variant="soft" onClick={() => onNewDoc("invoice", p)}><Plus size={12} /> {t("Invois", "Invoice")}</Button>
                      </div>
                      {mine.length > 0 && <ul className="mt-2 space-y-1 text-xs">
                        {mine.map((d) => <li key={d.id}><button type="button" className="font-mono hover:underline" onClick={() => onOpenDoc(d)}>{d.number || t("draf", "draft")}</button>
                          <span className="text-muted"> · {kindLabel(d.kind, L)} · {statusLabel(effectiveStatus(d, today), L)} · {money(d.total)}</span></li>)}
                      </ul>}
                    </div>
                  )}
                </li>
              );
            })}
            {!list.length && <li className="py-6 text-center text-sm text-muted">{t("Tiada projek lagi.", "No projects yet.")}</li>}
          </ul>
        </div>
      )}
    </Sheet>
  );
}

/* A project's four stages across (components/ui/timeline.tsx), read from its papers rather than kept as a field: the
   project is opened; a quotation is issued (accepted/declined said under it); an invoice is issued (outstanding under it);
   paid in full, or the project marked done. The current step is the first one still ahead. */
function projectStages(p, docs, today, t, L) {
  const mine = docs.filter((d) => d.project_id === p.id && d.status !== "draft" && d.status !== "void");
  const quotes = mine.filter((d) => d.kind === "quotation").sort((a, b) => String(a.issue_date).localeCompare(String(b.issue_date)));
  const invoices = mine.filter((d) => d.kind === "invoice").sort((a, b) => String(a.issue_date).localeCompare(String(b.issue_date)));
  const m = projectSummary(p.id, docs, today);
  const paidAll = invoices.length > 0 && invoices.every((d) => d.status === "paid");
  const lastPaid = invoices.filter((d) => d.paid_at).map((d) => d.paid_at).sort().slice(-1)[0];
  const closed = paidAll || p.status === "done";
  const q = quotes.slice(-1)[0], inv = invoices[0];
  const qState = q ? statusLabel(effectiveStatus(q, today), L) : "";
  return [
    { title: t("Projek dibuka", "Project opened"), date: p.start_date || (p.created_at || "").slice(0, 10), done: true,
      content: PROJECT_STATUS[p.status]?.[L] || p.status },
    { title: t("Sebut harga", "Quotation"), date: q?.issue_date, done: !!q,
      content: q ? `${q.number} · ${qState} · ${money(q.total)}` : t("belum ada", "none yet") },
    { title: t("Invois", "Invoice"), date: inv?.issue_date, done: !!inv,
      content: inv ? `${invoices.map((d) => d.number).join(", ")}${m.outstanding > 0 ? ` · ${t("baki", "due")} ${money(m.outstanding)}` : ""}` : t("belum ada", "none yet") },
    { title: paidAll ? t("Dibayar penuh", "Paid in full") : t("Selesai", "Done"), date: lastPaid ? lastPaid.slice(0, 10) : closed ? p.end_date : "", done: closed,
      content: closed ? `${t("dibayar", "paid")} ${money(m.paid)}` : p.end_date ? `${t("sasaran", "target")} ${fmtDate(p.end_date)}` : "" },
  ];
}

function ProjectStages({ project, docs, today, t, lang }) {
  const L = lang === "en" ? "en" : "bm";
  const stages = projectStages(project, docs, today, t, L);
  const firstOpen = stages.findIndex((s) => !s.done);
  return (
    <Timeline orientation="horizontal" value={firstOpen === -1 ? stages.length + 1 : firstOpen + 1} gap="[&:not(:last-child)]:pe-4" className="min-w-[520px] pt-1">
      {stages.map((s, i) => (
        <TimelineItem key={s.title} step={i + 1}>
          <TimelineIndicator>{s.done && <Check size={12} />}</TimelineIndicator>
          <TimelineSeparator />
          <TimelineHeader>
            <TimelineDate>{s.date ? fmtDate(s.date) : "—"}</TimelineDate>
            <TimelineTitle className="text-xs">{s.title}</TimelineTitle>
          </TimelineHeader>
          {s.content && <TimelineContent className="text-[11px] leading-snug">{s.content}</TimelineContent>}
        </TimelineItem>
      ))}
    </Timeline>
  );
}

/* A paper's history, newest at the bottom, every step completed: the same component drawn down. */
function DocHistory({ doc: d, events, t }) {
  const rows = [{ id: "created", at: d.created_at, label: t("draf dibuat", "draft created") },
    ...[...events].sort((a, b) => String(a.at).localeCompare(String(b.at))).map((ev) => ({ id: ev.id, at: ev.at, label: eventLabel(ev, t), failed: ev.kind === "email_failed" }))];
  return (
    <Timeline value={rows.length + 1} gap="[&:not(:last-child)]:pb-5" className="mt-1 text-xs">
      {rows.map((r, i) => (
        <TimelineItem key={r.id} step={i + 1} className="ms-6 gap-0.5">
          <TimelineIndicator className={`size-4 -left-6 ${r.failed ? "border-danger bg-danger" : ""}`}><Check size={9} /></TimelineIndicator>
          <TimelineSeparator className="-left-6 top-5 h-[calc(100%-1.25rem)]" />
          <TimelineHeader className="flex flex-wrap items-baseline gap-x-2">
            <TimelineDate className="mb-0 inline">{stampMYT(r.at)}</TimelineDate>
            <TimelineTitle className={`text-xs font-medium ${r.failed ? "text-danger" : ""}`}>{r.label}</TimelineTitle>
          </TimelineHeader>
        </TimelineItem>
      ))}
    </Timeline>
  );
}

function SettingsModal({ cfg, counters, onClose, onSave, busy, t }) {
  const [v, setV] = useState(cfg);
  const year = Number(isoDate().slice(0, 4));
  const [cnt, setCnt] = useState(() => KINDS.map((k) => {
    const p = cfg.prefix[k]; const row = counters.find((c) => c.prefix === p && Number(c.year) === year);
    return { kind: k, prefix: p, year, last: row ? Number(row.last) : 0 };
  }));
  const set = (sec, k) => (e) => setV({ ...v, [sec]: { ...v[sec], [k]: e.target.value } });
  const field = (sec, k, label, props = {}) => <label className="block"><Label>{label}</Label><Input value={v[sec][k] ?? ""} onChange={set(sec, k)} {...props} /></label>;
  return (
    <Sheet title={t("Tetapan Bil", "Billing settings")} onClose={onClose} width="max-w-4xl"
      actions={<Button size="sm" disabled={busy} onClick={() => onSave({ ...v, tax_rate: Number(v.tax_rate) || 0, email: { ...v.email, reminder_days: String(v.email.reminder_days).split(/[,\s]+/).map(Number).filter(Number.isFinite) } },
        cnt.map((c) => ({ prefix: v.prefix[c.kind], year: c.year, last: c.last })))}><Check size={14} /> {t("Simpan", "Save")}</Button>}>
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h4 className="text-sm font-medium">{t("Syarikat (pengeluar)", "Company (issuer)")}</h4>
          {field("company", "name", t("Nama", "Name"))}
          {field("company", "reg_no", t("No. pendaftaran", "Registration no."))}
          {field("company", "tagline", t("Slogan (kaki & atas)", "Tagline (footer & header)"))}
          {field("company", "footer", t("Baris kaki", "Footer line"))}
          <div className="grid gap-3 sm:grid-cols-2">{field("company", "email", "E-mel", { type: "email" })}{field("company", "phone", t("Telefon", "Phone"))}</div>
          {field("company", "website", t("Laman web", "Website"))}
          <label className="block"><Label>{t("Alamat (dicetak pada kertas)", "Address (printed)")}</Label><TextArea rows={2} value={v.company.address || ""} onChange={set("company", "address")} /></label>
          <div className="grid gap-3 sm:grid-cols-2">{field("company", "sst_no", t("No. SST (jika berdaftar: invois menjadi INVOIS CUKAI)", "SST no. (if registered: invoices become TAX INVOICE)"))}{field("company", "tin", "TIN (e-Invois)")}</div>
          {field("company", "signatory", t("Disediakan oleh (nama)", "Prepared by (name)"))}
          <h4 className="pt-2 text-sm font-medium">{t("Bank (pada invois)", "Bank (on invoices)")}</h4>
          {field("bank", "name", t("Nama bank", "Bank name"))}
          {field("bank", "account_name", t("Nama akaun", "Account name"))}
          {field("bank", "account_no", t("No. akaun", "Account no."))}
        </section>
        <section className="space-y-3">
          <h4 className="text-sm font-medium">{t("Penomboran", "Numbering")}</h4>
          <p className="text-xs text-muted">{t("Nombor seterusnya = awalan-tahun-(terakhir+1). Ubah 'terakhir' hanya untuk menyambung daripada nombor yang sudah digunakan di luar sistem.",
            "Next number = prefix-year-(last+1). Change 'last' only to continue from numbers already used outside the system.")}</p>
          {cnt.map((c, i) => (
            <div key={c.kind} className="grid grid-cols-[1fr_80px_90px_1fr] items-end gap-2 text-xs">
              <label className="block"><Label>{kindLabel(c.kind)} · {t("awalan", "prefix")}</Label><Input value={v.prefix[c.kind]} onChange={(e) => setV({ ...v, prefix: { ...v.prefix, [c.kind]: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") } })} /></label>
              <label className="block"><Label>{t("tahun", "year")}</Label><Input value={c.year} readOnly /></label>
              <label className="block"><Label>{t("terakhir", "last")}</Label><Input type="number" min="0" value={c.last} onChange={(e) => setCnt(cnt.map((x, j) => (j === i ? { ...x, last: Number(e.target.value) || 0 } : x)))} /></label>
              <div className="pb-2 font-mono text-muted">→ {v.prefix[c.kind]}-{c.year}-{String(c.last + 1).padStart(3, "0")}</div>
            </div>
          ))}
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="block"><Label>{t("Sebut harga sah (hari)", "Quotation valid (days)")}</Label><Input type="number" min="1" value={v.days.quotation_valid} onChange={(e) => setV({ ...v, days: { ...v.days, quotation_valid: Number(e.target.value) || 30 } })} /></label>
            <label className="block"><Label>{t("Invois tempoh (hari)", "Invoice due (days)")}</Label><Input type="number" min="0" value={v.days.invoice_due} onChange={(e) => setV({ ...v, days: { ...v.days, invoice_due: Number(e.target.value) || 0 } })} /></label>
            <label className="block"><Label>{t("Cukai lalai %", "Default tax %")}</Label><Input type="number" min="0" step="0.01" value={v.tax_rate} onChange={(e) => setV({ ...v, tax_rate: e.target.value })} /></label>
          </div>
          <label className="block"><Label>{t("Bahasa lalai dokumen dan e-mel (setiap pelanggan dan kertas boleh ditukar sendiri)", "Default language of papers and e-mails (each client and paper can still be switched)")}</Label>
            <Select value={v.lang || "en"} onChange={(val) => setV({ ...v, lang: val })} options={[["en", "English"], ["bm", "Bahasa Malaysia"]]} className="w-full" /></label>
          <h4 className="pt-2 text-sm font-medium">{t("Terma lalai", "Default terms")}</h4>
          {KINDS.map((k) => <label key={k} className="block"><Label>{kindLabel(k)}</Label><TextArea rows={3} value={v.terms[k] || ""} onChange={(e) => setV({ ...v, terms: { ...v.terms, [k]: e.target.value } })} /></label>)}
          <h4 className="pt-2 text-sm font-medium">{t("E-mel", "E-mail")}</h4>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!v.email.auto_send} onChange={(e) => setV({ ...v, email: { ...v.email, auto_send: e.target.checked } })} />{t("Hantar e-mel secara automatik sebaik dikeluarkan", "E-mail automatically on issue")}</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!v.email.auto_reminders} onChange={(e) => setV({ ...v, email: { ...v.email, auto_reminders: e.target.checked } })} />{t("Peringatan automatik untuk invois lewat", "Automatic reminders for late invoices")}</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!v.email.cc_self} onChange={(e) => setV({ ...v, email: { ...v.email, cc_self: e.target.checked } })} />{t("Salinan setiap e-mel ke e-mel syarikat", "Copy every e-mail to the company address")}</label>
          <label className="block"><Label>{t("Hari peringatan berbanding tarikh akhir (negatif = sebelum)", "Reminder days relative to due (negative = before)")}</Label>
            <Input value={Array.isArray(v.email.reminder_days) ? v.email.reminder_days.join(", ") : v.email.reminder_days} onChange={(e) => setV({ ...v, email: { ...v.email, reminder_days: e.target.value } })} /></label>
          <p className="text-xs text-muted">{t("E-mel keluar dari Gmail yang disambung di Composio (akaun syarikat). Pekerja berjalan dalam seminit dua selepas setiap Hantar, dan setiap pagi 09:15 untuk peringatan.",
            "E-mail leaves from the Gmail connected in Composio (the company account). The worker runs within a minute or two of every Send, and every morning at 09:15 for reminders.")}</p>
        </section>
      </div>
    </Sheet>
  );
}

/* Print through a hidden frame: the browser's own print dialog, where "Save as PDF" lives (the FAQ export does the same). */
function PrintFrame({ html, onDone }) {
  useEffect(() => {
    const frame = document.createElement("iframe");
    frame.style.position = "fixed"; frame.style.right = "0"; frame.style.bottom = "0"; frame.style.width = "0"; frame.style.height = "0"; frame.style.border = "0";
    document.body.appendChild(frame);
    const w = frame.contentWindow;
    const finish = () => { setTimeout(() => { try { document.body.removeChild(frame); } catch { /* gone */ } onDone(); }, 500); };
    w.addEventListener("afterprint", finish);
    w.document.open(); w.document.write(html); w.document.close();
    const go = () => { try { w.focus(); w.print(); } catch { finish(); } };
    if (w.document.readyState === "complete") setTimeout(go, 300); else w.addEventListener("load", () => setTimeout(go, 300));
    const safety = setTimeout(finish, 60_000);
    return () => clearTimeout(safety);
  }, [html, onDone]);
  return null;
}

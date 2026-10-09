import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, ExternalLink, Mail, MailCheck, MessageCircle, Pencil, Plus, Send, Trash2, UserPlus, Users } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { stampMYT } from "../lib/format";
import { fmtDate } from "../lib/billing";
import { ACTIVITY_KINDS, STAGES, STAGE_WORDS, audienceOf, blankCampaign, blankContact, campaignRow, contactRow, crmSummary,
  mailable, merge, parseTags, validateCampaign, validateContact, waLink } from "../lib/crm";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Modal, Segmented, Select, TextArea } from "../components/ui/Field";

/* CRM (supabase/031_crm.sql, EspoCRM-shaped): contacts with a stage, what happened with each, and campaigns of marketing
   material that go out by themselves from Wan's Gmail (backend/semasa/crm.py) to the contacts who agreed to hear from
   him. The database's semasa_crm_queue decides who gets a campaign; lib/crm.js audienceOf is the same rule, so the composer
   says "goes to N of M" before the click. Nothing here sends a mail directly: a Send writes outbox rows and the worker
   sends them, with the PDPA footer and the unsubscribe link under every one. */

const today = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
const STAGE_TONE = { lead: "bg-surface-2 text-muted", prospect: "bg-accent/10 text-accent", client: "bg-ok/10 text-ok", dormant: "bg-warn/10 text-warn", lost: "bg-danger/10 text-danger" };
const STATUS_WORDS = { draft: ["Draf", "Draft"], scheduled: ["Dijadual", "Scheduled"], sending: ["Menghantar", "Sending"], sent: ["Dihantar", "Sent"], paused: ["Dijeda", "Paused"], deleting: ["Memadam", "Deleting"] };
const KIND_WORDS = { note: ["Nota", "Note"], call: ["Panggilan", "Call"], meeting: ["Mesyuarat", "Meeting"], email: ["E-mel", "E-mail"], whatsapp: ["WhatsApp", "WhatsApp"],
  campaign: ["Kempen", "Campaign"], unsubscribe: ["Berhenti melanggan", "Unsubscribed"], stage: ["Peringkat", "Stage"] };

export default function CrmTab({ user, settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (map, k) => (map[k] || [k, k])[L];
  const contactsT = useTable(TABLES.crmContacts, { enabled: true, order: "updated_at", limit: 3000 });
  const campaignsT = useTable(TABLES.crmCampaigns, { enabled: true, order: "updated_at", limit: 500 });
  const outboxT = useTable(TABLES.crmOutbox, { enabled: true, order: "created_at", limit: 3000 });
  const activitiesT = useTable(TABLES.crmActivities, { enabled: true, order: "at", limit: 3000 });
  const [view, setView] = useState("contacts");
  const [stage, setStage] = useState("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);         // a contact in the form
  const [open, setOpen] = useState(null);               // a contact's record (activities)
  const [composing, setComposing] = useState(null);     // a campaign in the composer
  const [board, setBoard] = useState(null);             // a WhatsApp campaign's blast board
  const [waId, setWaId] = useState(null);               // the WhatsApp sender id being edited
  const [busy, setBusy] = useState("");
  const day = today();
  const missing = /semasa_crm_/.test(contactsT.error || "");
  const sum = useMemo(() => crmSummary(contactsT.rows, outboxT.rows, day), [contactsT.rows, outboxT.rows, day]);
  const list = useMemo(() => contactsT.rows
    .filter((k) => !stage || k.stage === stage)
    .filter((k) => !q || `${k.name} ${k.company} ${k.email} ${k.phone} ${(k.tags || []).join(" ")}`.toLowerCase().includes(q.toLowerCase())), [contactsT.rows, stage, q]);
  const allTags = useMemo(() => [...new Set(contactsT.rows.flatMap((k) => k.tags || []))].sort(), [contactsT.rows]);
  const crmCfg = settings?.crm || {};
  const waApi = Boolean(crmCfg.whatsapp_phone_number_id);
  const testTo = crmCfg.test_to || settings?.billing?.company?.email || user?.email || "";

  const reload = () => { contactsT.reload(); campaignsT.reload(); outboxT.reload(); activitiesT.reload(); };
  const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { onToast(e.message || String(e), "danger"); } };

  const saveContact = guard(async (form) => {
    const bad = validateContact(form);
    if (bad.length) return onToast(t("Lengkapkan: {f}", "Fill in: {f}", { f: bad.join(", ") }), "danger");
    setBusy("contact");
    try {
      const row = contactRow(form);
      const before = form.id ? contactsT.rows.find((k) => k.id === form.id) : null;
      if (row.consent && !(before?.consent)) row.consent_at = new Date().toISOString();   // a new consent is dated when it is given
      if (!row.consent) { row.consent_at = null; }
      const qy = form.id ? supabase.from(TABLES.crmContacts).update(row).eq("id", form.id)
        : supabase.from(TABLES.crmContacts).insert({ ...row, created_by: user?.id || null });
      const { data, error } = await qy.select("id");
      if (error) throw new Error(/semasa_crm_contacts_email_key/.test(errText(error)) ? t("E-mel ini sudah ada pada kenalan lain.", "This e-mail is already on another contact.") : errText(error));
      const id = form.id || data?.[0]?.id;
      if (before && before.stage !== row.stage && id) {
        await supabase.from(TABLES.crmActivities).insert({ contact_id: id, kind: "stage", title: `${w(STAGE_WORDS, before.stage)} → ${w(STAGE_WORDS, row.stage)}`, created_by: user?.id || null });
      }
      setEditing(null); reload(); onToast(t("Disimpan.", "Saved."), "ok");
    } finally { setBusy(""); }
  });
  const removeContact = guard(async (k) => {
    if (!window.confirm(t("Padam {n}? Sejarahnya ikut dipadam.", "Delete {n}? Their history goes too.", { n: k.name }))) return;
    const { error } = await supabase.from(TABLES.crmContacts).delete().eq("id", k.id);
    if (error) throw new Error(errText(error));
    setOpen(null); reload(); onToast(t("Dipadam.", "Deleted."), "info");
  });
  const addActivity = guard(async (k, kind, title) => {
    if (!title.trim()) return;
    const { error } = await supabase.from(TABLES.crmActivities).insert({ contact_id: k.id, kind, title: title.trim(), created_by: user?.id || null });
    if (error) throw new Error(errText(error));
    await supabase.from(TABLES.crmContacts).update({ last_contact_at: new Date().toISOString() }).eq("id", k.id);
    reload();
  });
  const saveCampaign = guard(async (form, then) => {
    const bad = validateCampaign(form);
    if (bad.length) { onToast(t("Lengkapkan: {f}", "Fill in: {f}", { f: bad.join(", ") }), "danger"); return null; }
    const row = campaignRow(form);
    const qy = form.id ? supabase.from(TABLES.crmCampaigns).update(row).eq("id", form.id)
      : supabase.from(TABLES.crmCampaigns).insert({ ...row, created_by: user?.id || null });
    const { data, error } = await qy.select("id");
    if (error) throw new Error(errText(error));
    const id = form.id || data?.[0]?.id;
    // a campaign already queued: the words on every row still pending follow the edit (032 semasa_crm_refill)
    if (form.id && ["scheduled", "sending", "paused"].includes(form.status)) {
      const { data: r, error: e2 } = await supabase.rpc("semasa_crm_refill", { p_campaign: id });
      if (e2) throw new Error(errText(e2));
      if (r?.refilled) onToast(t("{n} mesej yang masih menunggu dikemas kini.", "{n} messages still waiting were updated.", { n: r.refilled }), "info");
    }
    campaignsT.reload();
    if (then) await then(id);
    return id;
  });
  const queueCampaign = guard(async (form) => {
    setBusy("queue");
    try {
      await saveCampaign(form, async (id) => {
        const { data, error } = await supabase.rpc("semasa_crm_queue", { p_campaign: id });
        if (error) throw new Error(errText(error));
        const r = data || {};
        const wa = form.channel === "whatsapp";
        onToast(wa
          ? t("{q} mesej WhatsApp digiliran · {c} tanpa kebenaran · {e} tanpa nombor · {a} sudah ada", "{q} WhatsApp messages queued · {c} without consent · {e} without a number · {a} already had it",
            { q: r.queued ?? 0, c: r.skipped_no_consent ?? 0, e: r.skipped_no_contact ?? 0, a: r.already ?? 0 })
          : t("{q} e-mel digiliran · {c} tanpa kebenaran · {e} tanpa e-mel · {a} sudah ada", "{q} e-mails queued · {c} without consent · {e} without e-mail · {a} already had it",
            { q: r.queued ?? 0, c: r.skipped_no_consent ?? 0, e: r.skipped_no_email ?? 0, a: r.already ?? 0 }), "ok");
        setComposing(null); reload();
        if (wa && !waApi) setBoard(campaignsT.rows.find((c) => c.id === id) || { id, name: form.name, channel: "whatsapp" });
      });
    } finally { setBusy(""); }
  });
  const testSend = guard(async (form) => {
    if (form.channel === "whatsapp") return onToast(t("Ujian WhatsApp: hantar kepada diri sendiri dari papan blast selepas digiliran.", "WhatsApp test: send one to yourself from the blast board once it is queued."), "info");
    if (!testTo) return onToast(t("Tiada alamat ujian: isi e-mel syarikat dalam Tetapan Bil.", "No test address: fill in the company e-mail under Bil settings."), "danger");
    setBusy("test");
    try {
      await saveCampaign(form, async (id) => {
        const sample = contactsT.rows.find(mailable) || { name: "Wan", company: "WS Regulab Solutions" };
        // a test needs a contact row to hang off; it goes to Wan himself and is never counted (crm.py)
        const me = contactsT.rows.find((k) => k.email?.toLowerCase() === testTo.toLowerCase());
        let contactId = me?.id;
        if (!contactId) {
          const { data, error } = await supabase.from(TABLES.crmContacts).insert({ name: "Wan (ujian)", email: testTo, stage: "client", consent: false, source: "test", notes: "Row for test sends", created_by: user?.id || null }).select("id");
          if (error) throw new Error(errText(error));
          contactId = data[0].id;
        }
        const { error } = await supabase.from(TABLES.crmOutbox).upsert({ campaign_id: id, contact_id: contactId, to_email: testTo, is_test: true, status: "pending",
          subject: `[UJIAN] ${merge(form.subject, sample)}`, body: merge(form.body, sample) }, { onConflict: "campaign_id,contact_id,is_test" });
        if (error) throw new Error(errText(error));
        onToast(t("Ujian digiliran ke {e}; pekerja menghantar dalam seminit.", "Test queued to {e}; the worker sends it within a minute.", { e: testTo }), "ok");
        outboxT.reload();
      });
    } finally { setBusy(""); }
  });
  const setCampaignStatus = guard(async (c, status) => {
    const { error } = await supabase.from(TABLES.crmCampaigns).update({ status }).eq("id", c.id);
    if (error) throw new Error(errText(error));
    campaignsT.reload();
  });
  const removeCampaign = guard(async (c) => {
    const sentMail = outboxT.rows.filter((o) => o.campaign_id === c.id && o.channel !== "whatsapp" && o.status === "sent" && o.result?.id).length;
    const sentWa = outboxT.rows.filter((o) => o.campaign_id === c.id && o.channel === "whatsapp" && o.status === "sent").length;
    if (!window.confirm(t("Padam kempen {n}?", "Delete campaign {n}?", { n: c.name }))) return;
    let trash = false;
    if (sentMail) trash = window.confirm(t("{n} e-mel sudah dihantar. Alihkan juga ke Sampah Gmail? (OK = ya, pekerja memadamnya satu persatu; Batal = padam dari sistem sahaja)",
      "{n} e-mails were already sent. Also move them to Gmail's Trash? (OK = yes, the worker trashes them one by one; Cancel = delete from the system only)", { n: sentMail }));
    if (sentWa) onToast(t("{n} mesej WhatsApp sudah dihantar tidak boleh ditarik balik; ia dipadam dari sistem sahaja.", "{n} WhatsApp messages already sent cannot be recalled; they are deleted from the system only.", { n: sentWa }), "info");
    const { data, error } = await supabase.rpc("semasa_crm_delete", { p_campaign: c.id, p_trash: trash });
    if (error) throw new Error(errText(error));
    if (data?.trashing) onToast(t("{n} e-mel dialihkan ke Sampah Gmail oleh pekerja; kempen hilang selepas itu.", "{n} e-mails are being moved to Gmail's Trash by the worker; the campaign goes once that is done.", { n: data.trashing }), "ok");
    reload();
  });
  const removeRow = guard(async (o) => {
    const mail = o.channel !== "whatsapp" && o.status === "sent" && o.result?.id;
    const q = mail ? t("Padam e-mel ini dari sistem dan alihkan ke Sampah Gmail?", "Delete this e-mail from the system and move it to Gmail's Trash?")
      : o.channel === "whatsapp" && o.status === "sent" ? t("Mesej WhatsApp yang dihantar tidak boleh ditarik balik. Padam dari sistem sahaja?", "A sent WhatsApp message cannot be recalled. Delete it from the system only?")
      : t("Padam mesej ini?", "Delete this message?");
    if (!window.confirm(q)) return;
    const { error } = await supabase.rpc("semasa_crm_delete_row", { p_row: o.id, p_trash: true });
    if (error) throw new Error(errText(error));
    outboxT.reload(); campaignsT.reload();
  });
  const markSent = guard(async (o) => {
    const { error } = await supabase.from(TABLES.crmOutbox).update({ status: "sent", sent_at: new Date().toISOString(), result: { manual: true }, error: "" }).eq("id", o.id);
    if (error) throw new Error(errText(error));
    await supabase.from(TABLES.crmContacts).update({ last_contact_at: new Date().toISOString() }).eq("id", o.contact_id);
    await supabase.from(TABLES.crmActivities).insert({ contact_id: o.contact_id, kind: "campaign", title: `WhatsApp kempen (manual): ${o.subject}`, detail: { outbox_id: o.id, channel: "whatsapp", manual: true }, created_by: user?.id || null });
    outboxT.reload(); activitiesT.reload();
  });
  const saveWaId = guard(async () => {
    if (!save) return;
    await save("crm", { ...crmCfg, whatsapp_phone_number_id: String(waId || "").trim() });
    setWaId(null); onToast(t("Disimpan. Pekerja menghantar WhatsApp sendiri dari larian seterusnya.", "Saved. The worker sends WhatsApp itself from the next run."), "ok");
  });

  const tiles = [
    { label: t("Kenalan", "Contacts"), value: String(sum.total), icon: Users, hint: STAGES.map((s) => `${sum.byStage[s] || 0} ${w(STAGE_WORDS, s).toLowerCase()}`).slice(0, 3).join(" · ") },
    { label: t("Boleh dihantar e-mel", "Mailable"), value: String(sum.consenting), icon: MailCheck, hint: sum.waWaiting ? t("{n} WhatsApp menunggu di papan blast", "{n} WhatsApp waiting on the blast board", { n: sum.waWaiting }) : t("{n} berhenti melanggan", "{n} unsubscribed", { n: sum.unsubscribed }), tone: sum.waWaiting ? "warn" : "" },
    { label: t("Dihantar 30 hari", "Sent in 30 days"), value: String(sum.sent30), icon: Send, hint: sum.failed ? t("{n} gagal", "{n} failed", { n: sum.failed }) : t("tiada yang gagal", "none failed"), tone: sum.failed ? "danger" : "" },
    { label: t("Tindakan tertunggak", "Actions due"), value: String(sum.actionsDue), icon: CalendarClock, hint: t("tarikh susulan sudah tiba", "follow-up dates reached"), tone: sum.actionsDue ? "warn" : "" },
  ];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">CRM</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Kenalan, peringkat, apa yang berlaku, dan kempen e-mel yang keluar sendiri dari Gmail anda kepada mereka yang bersetuju. Setiap e-mel pemasaran membawa pautan berhenti melanggan (PDPA 2010).",
            "Contacts, stages, what happened, and e-mail campaigns that go out by themselves from your Gmail to the people who agreed. Every marketing e-mail carries an unsubscribe link (PDPA 2010).")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Segmented value={view} onChange={setView} options={[["contacts", t("Kenalan", "Contacts")], ["campaigns", t("Kempen", "Campaigns")]]} />
          {view === "contacts"
            ? <Button onClick={() => setEditing(blankContact())}><UserPlus size={14} /> {t("Kenalan", "Contact")}</Button>
            : <Button onClick={() => setComposing(blankCampaign())}><Plus size={14} /> {t("Kempen", "Campaign")}</Button>}
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/031_crm.sql sekali.", "The tables are not there yet: run supabase/031_crm.sql once.")}</p>}
      {contactsT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{contactsT.error}</p>}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((s) => (
          <Card key={s.label} className={`p-4 ${s.tone === "danger" ? "border-danger/40" : s.tone === "warn" ? "border-warn/40" : ""}`}>
            <div className="flex items-center justify-between"><span className="text-[11px] uppercase tracking-widest text-muted">{s.label}</span><s.icon size={16} className="text-muted" /></div>
            <p className={`mt-2 font-display text-2xl tabular-nums ${s.tone === "danger" ? "text-danger" : ""}`}>{s.value}</p>
            <p className="mt-0.5 text-xs text-muted">{s.hint}</p>
          </Card>
        ))}
      </div>

      {view === "contacts" ? (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Input className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari nama, syarikat, e-mel, tag…", "Search name, company, e-mail, tag…")} />
            <div className="flex flex-wrap gap-1">
              <button type="button" onClick={() => setStage("")} className={`rounded-pill px-3 py-1 text-xs ${!stage ? "bg-ink text-surface" : "bg-surface-2 text-muted"}`}>{t("Semua", "All")} ({contactsT.rows.length})</button>
              {STAGES.map((s) => <button type="button" key={s} onClick={() => setStage(s)} className={`rounded-pill px-3 py-1 text-xs ${stage === s ? "bg-ink text-surface" : STAGE_TONE[s]}`}>{w(STAGE_WORDS, s)} ({sum.byStage[s] || 0})</button>)}
            </div>
          </div>
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-[11px] uppercase tracking-widest text-muted">
                <tr><th className="px-4 py-3">{t("Kenalan", "Contact")}</th><th className="px-3 py-3">{t("Peringkat", "Stage")}</th><th className="px-3 py-3">{t("E-mel pemasaran", "Marketing e-mail")}</th>
                  <th className="px-3 py-3">{t("Susulan", "Follow-up")}</th><th className="px-3 py-3">{t("Terakhir", "Last contact")}</th><th className="px-3 py-3" /></tr>
              </thead>
              <tbody>
                {list.map((k) => (
                  <tr key={k.id} className="cursor-pointer border-t border-line/70 align-top hover:bg-surface-2/60" onClick={() => setOpen(k)}>
                    <td className="px-4 py-3">
                      <div className="font-medium">{k.name}{k.company ? <span className="text-muted"> · {k.company}</span> : null}</div>
                      <div className="text-xs text-muted">{[k.email, k.phone, k.source].filter(Boolean).join(" · ")}</div>
                      {k.tags?.length ? <div className="mt-1 flex flex-wrap gap-1">{k.tags.map((tag) => <span key={tag} className="rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] text-muted">{tag}</span>)}</div> : null}
                    </td>
                    <td className="px-3 py-3"><span className={`rounded-pill px-2 py-0.5 text-[11px] ${STAGE_TONE[k.stage]}`}>{w(STAGE_WORDS, k.stage)}</span></td>
                    <td className="px-3 py-3 text-xs">{k.unsubscribed_at ? <span className="text-danger">{t("Berhenti melanggan", "Unsubscribed")} {fmtDate(k.unsubscribed_at.slice(0, 10))}</span>
                      : k.consent ? <span className="text-ok">{t("Ya", "Yes")}{k.consent_source ? ` · ${k.consent_source}` : ""}</span>
                      : <span className="text-muted">{t("Tiada kebenaran", "No consent")}</span>}</td>
                    <td className="px-3 py-3 text-xs">{k.next_action ? <span className={k.next_action_at && k.next_action_at <= day ? "text-warn" : ""}>{k.next_action}{k.next_action_at ? ` · ${fmtDate(k.next_action_at)}` : ""}</span> : <span className="text-muted">—</span>}</td>
                    <td className="px-3 py-3 text-xs text-muted">{k.last_contact_at ? stampMYT(k.last_contact_at) : "—"}</td>
                    <td className="px-3 py-3"><div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                      <Button size="sm" variant="ghost" onClick={() => setEditing({ ...blankContact(), ...k, next_action_at: k.next_action_at || "" })} title={t("Sunting", "Edit")}><Pencil size={13} /></Button>
                      <Button size="sm" variant="ghost" onClick={() => removeContact(k)} title={t("Padam", "Delete")}><Trash2 size={13} /></Button>
                    </div></td>
                  </tr>
                ))}
                {!list.length && !contactsT.loading && <tr><td colSpan={6} className="px-4 py-8 text-center text-sm text-muted">{t("Tiada kenalan. Tekan Kenalan untuk menambah.", "No contacts. Press Contact to add one.")}</td></tr>}
              </tbody>
            </table>
          </Card>
        </>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted">
            <MessageCircle size={13} />
            {waApi ? t("WhatsApp: pekerja menghantar sendiri melalui WhatsApp Business (ID nombor {id}).", "WhatsApp: the worker sends itself through WhatsApp Business (number id {id}).", { id: crmCfg.whatsapp_phone_number_id })
              : t("WhatsApp: tiada API disambung, jadi kempen WhatsApp jadi papan blast (klik satu persatu, perkataan sudah diisi).", "WhatsApp: no API connected, so a WhatsApp campaign becomes a blast board (click one by one, words filled in).")}
            {save && (waId == null
              ? <button type="button" className="underline" onClick={() => setWaId(crmCfg.whatsapp_phone_number_id || "")}>{waApi ? t("tukar", "change") : t("sambung API", "connect the API")}</button>
              : <span className="flex items-center gap-1"><Input className="w-56" value={waId} onChange={(e) => setWaId(e.target.value)} placeholder={t("Phone number ID dari Meta", "Phone number ID from Meta")} />
                <Button size="sm" onClick={saveWaId}>{t("Simpan", "Save")}</Button><Button size="sm" variant="ghost" onClick={() => setWaId(null)}>{t("Batal", "Cancel")}</Button></span>)}
          </div>
          <CampaignList campaigns={campaignsT.rows} contacts={contactsT.rows} outbox={outboxT.rows} t={t} w={w} onEdit={(c) => setComposing({ ...blankCampaign(), ...c, send_at: c.send_at ? toLocalInput(c.send_at) : "" })}
            onStatus={setCampaignStatus} onDelete={removeCampaign} onBoard={(c) => setBoard(c)} />
        </>
      )}

      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title={editing?.id ? t("Sunting kenalan", "Edit contact") : t("Kenalan baharu", "New contact")}>
        {editing && <ContactForm form={editing} setForm={setEditing} onSave={() => saveContact(editing)} busy={busy === "contact"} t={t} w={w} allTags={allTags} />}
      </Modal>
      <Modal open={Boolean(open)} onClose={() => setOpen(null)} title={open?.name || ""}>
        {open && <ContactRecord k={contactsT.rows.find((x) => x.id === open.id) || open} activities={activitiesT.rows.filter((a) => a.contact_id === open.id)} outbox={outboxT.rows.filter((o) => o.contact_id === open.id && !o.is_test)}
          campaigns={campaignsT.rows} t={t} w={w} onAdd={(kind, title) => addActivity(open, kind, title)} onEdit={() => { setEditing({ ...blankContact(), ...open, next_action_at: open.next_action_at || "" }); setOpen(null); }}
          onDeleteRow={removeRow} />}
      </Modal>
      <Modal open={Boolean(board)} onClose={() => setBoard(null)} title={t("Papan blast WhatsApp · {n}", "WhatsApp blast board · {n}", { n: board?.name || "" })}>
        {board && <BlastBoard rows={outboxT.rows.filter((o) => o.campaign_id === board.id && !o.is_test)} contacts={contactsT.rows} t={t} onSent={markSent} waApi={waApi} />}
      </Modal>
      <Modal open={Boolean(composing)} onClose={() => setComposing(null)} title={composing?.id ? t("Sunting kempen", "Edit campaign") : t("Kempen baharu", "New campaign")}>
        {composing && <CampaignComposer form={composing} setForm={setComposing} contacts={contactsT.rows} allTags={allTags} busy={busy} testTo={testTo} t={t} w={w}
          onSave={() => saveCampaign(composing, () => { setComposing(null); onToast(t("Disimpan sebagai draf.", "Saved as a draft."), "ok"); })}
          onTest={() => testSend(composing)} onQueue={() => queueCampaign(composing)} />}
      </Modal>
    </main>
  );
}

const toLocalInput = (iso) => { const d = new Date(new Date(iso).getTime() + 8 * 3600_000); return d.toISOString().slice(0, 16); };   // the picker shows Malaysia time

function ContactForm({ form, setForm, onSave, busy, t, w, allTags }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e });
  return (
    <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); onSave(); }}>
      <label><Label>{t("Nama", "Name")}</Label><Input value={form.name} onChange={set("name")} /></label>
      <label><Label>{t("Syarikat", "Company")}</Label><Input value={form.company} onChange={set("company")} /></label>
      <label><Label>E-mel</Label><Input type="email" value={form.email} onChange={set("email")} /></label>
      <label><Label>{t("Telefon", "Phone")}</Label><Input value={form.phone} onChange={set("phone")} /></label>
      <label><Label>{t("Peringkat", "Stage")}</Label><Select className="w-full" value={form.stage} onChange={set("stage")} options={STAGES.map((s) => [s, w(STAGE_WORDS, s)])} /></label>
      <label><Label>{t("Sumber", "Source")}</Label><Input value={form.source} onChange={set("source")} placeholder={t("rujukan · laman web · LinkedIn · acara", "referral · website · LinkedIn · event")} /></label>
      <label><Label>{t("Tag", "Tags")} <span className="font-normal opacity-70">({t("dipisah koma", "comma-separated")})</span></Label>
        <Input value={Array.isArray(form.tags) ? form.tags.join(", ") : form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} list="crm-tags" />
        <datalist id="crm-tags">{allTags.map((x) => <option key={x} value={x} />)}</datalist></label>
      <label><Label>{t("Bahasa e-mel", "E-mail language")}</Label><Select className="w-full" value={form.lang} onChange={set("lang")} options={[["bm", "Bahasa Malaysia"], ["en", "English"]]} /></label>
      <div className="rounded-tile border border-line bg-surface-2/60 p-3 sm:col-span-2">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form.consent)} onChange={set("consent")} /> {t("Bersetuju menerima e-mel pemasaran", "Agreed to receive marketing e-mail")}</label>
        {form.consent && <label className="mt-2 block"><Label hint={t("PDPA: bila dan bagaimana", "PDPA: when and how")}>{t("Bukti kebenaran", "Consent source")}</Label>
          <Input value={form.consent_source} onChange={set("consent_source")} placeholder={t("cth: borang laman web 9 Okt · WhatsApp 3 Okt · pelanggan sedia ada", "e.g. website form 9 Oct · WhatsApp 3 Oct · existing client")} /></label>}
        {form.unsubscribed_at && <p className="mt-2 text-xs text-danger">{t("Berhenti melanggan pada {d}. Kebenaran baharu perlu diminta semula; ini tidak boleh diubah dari sini.", "Unsubscribed on {d}. A new consent has to be asked for again; this cannot be undone here.", { d: fmtDate(form.unsubscribed_at.slice(0, 10)) })}</p>}
      </div>
      <label><Label>{t("Tindakan seterusnya", "Next action")}</Label><Input value={form.next_action} onChange={set("next_action")} placeholder={t("hubungi semula tentang sebut harga", "call back about the quotation")} /></label>
      <label><Label>{t("Pada", "On")}</Label><Input type="date" value={form.next_action_at || ""} onChange={set("next_action_at")} /></label>
      <label className="sm:col-span-2"><Label>{t("Nota", "Notes")}</Label><TextArea rows={2} value={form.notes} onChange={set("notes")} /></label>
      <div className="flex justify-end gap-2 sm:col-span-2"><Button type="submit" disabled={busy}>{t("Simpan", "Save")}</Button></div>
    </form>
  );
}

function ContactRecord({ k, activities, outbox, campaigns, t, w, onAdd, onEdit, onDeleteRow }) {
  const [kind, setKind] = useState("note");
  const [title, setTitle] = useState("");
  const nameOf = (id) => campaigns.find((c) => c.id === id)?.name || "—";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2 text-sm">
        <div>
          <p>{[k.company, k.email, k.phone].filter(Boolean).join(" · ")}</p>
          <p className="text-xs text-muted"><span className={`rounded-pill px-2 py-0.5 ${STAGE_TONE[k.stage]}`}>{w(STAGE_WORDS, k.stage)}</span> {k.source ? ` · ${k.source}` : ""}{k.consent ? ` · ${t("kebenaran", "consent")}: ${k.consent_source || "✓"}` : ` · ${t("tiada kebenaran pemasaran", "no marketing consent")}`}</p>
          {k.notes && <p className="mt-1 whitespace-pre-wrap text-xs text-muted">{k.notes}</p>}
        </div>
        <Button size="sm" variant="ghost" onClick={onEdit}><Pencil size={13} /> {t("Sunting", "Edit")}</Button>
      </div>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); onAdd(kind, title); setTitle(""); }}>
        <Select value={kind} onChange={setKind} options={ACTIVITY_KINDS.map((x) => [x, w(KIND_WORDS, x)])} />
        <Input className="min-w-0 flex-1" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t("Apa yang berlaku…", "What happened…")} />
        <Button type="submit" size="sm" disabled={!title.trim()}><Plus size={13} /></Button>
      </form>
      <ol className="max-h-72 space-y-2 overflow-y-auto text-sm">
        {[...activities.map((a) => ({ at: a.at, kind: a.kind, title: a.title })), ...outbox.map((o) => ({ at: o.sent_at || o.created_at, kind: o.channel === "whatsapp" ? "whatsapp" : "email", row: o,
          title: `${o.trash_requested ? "🗑" : o.status === "sent" ? "✓" : o.status === "error" ? "✗" : "…"} ${nameOf(o.campaign_id)}: ${o.subject}` }))]
          .sort((a, b) => String(b.at).localeCompare(String(a.at))).map((a, i) => (
            <li key={i} className="flex items-start gap-3"><span className="w-28 shrink-0 text-xs text-muted">{stampMYT(a.at)}</span>
              <span className="min-w-0 flex-1"><span className="text-xs text-muted">{w(KIND_WORDS, a.kind)} · </span>{a.title}</span>
              {a.row && onDeleteRow && !a.row.trash_requested && <button type="button" className="shrink-0 text-muted hover:text-danger" title={t("Padam (dan alih ke Sampah Gmail jika e-mel)", "Delete (and move to Gmail's Trash if an e-mail)")} onClick={() => onDeleteRow(a.row)}><Trash2 size={13} /></button>}
            </li>
          ))}
        {!activities.length && !outbox.length && <li className="text-xs text-muted">{t("Tiada sejarah lagi.", "No history yet.")}</li>}
      </ol>
    </div>
  );
}

function CampaignList({ campaigns, contacts, outbox, t, w, onEdit, onStatus, onDelete, onBoard }) {
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-[11px] uppercase tracking-widest text-muted">
          <tr><th className="px-4 py-3">{t("Kempen", "Campaign")}</th><th className="px-3 py-3">{t("Jenis", "Kind")}</th><th className="px-3 py-3">{t("Penerima", "Audience")}</th>
            <th className="px-3 py-3">{t("Bila", "When")}</th><th className="px-3 py-3">{t("Status", "Status")}</th><th className="px-3 py-3">{t("Dihantar", "Sent")}</th><th className="px-3 py-3" /></tr>
        </thead>
        <tbody>
          {campaigns.map((c) => {
            const aud = audienceOf(c, contacts);
            const mine = outbox.filter((o) => o.campaign_id === c.id && !o.is_test);
            const pending = mine.filter((o) => ["pending", "working"].includes(o.status)).length;
            return (
              <tr key={c.id} className="border-t border-line/70 align-top">
                <td className="px-4 py-3"><div className="font-medium">{c.name}</div><div className="text-xs text-muted">{c.subject}</div></td>
                <td className="px-3 py-3 text-xs"><span className="mr-1 inline-flex items-center gap-1">{c.channel === "whatsapp" ? <><MessageCircle size={12} /> WhatsApp</> : <><Mail size={12} /> E-mel</>}</span><br />{c.kind === "welcome" ? t("Alu-aluan (automatik)", "Welcome (automatic)") : t("Siaran", "Broadcast")}</td>
                <td className="px-3 py-3 text-xs">{t("{n} daripada {m}", "{n} of {m}", { n: aud.send.length, m: aud.named.length })}
                  <div className="text-muted">{[(c.audience?.stages || []).map((s) => w(STAGE_WORDS, s)).join("/"), (c.audience?.tags || []).join("/"), c.audience?.lang].filter(Boolean).join(" · ") || t("semua yang bersetuju", "everyone consenting")}</div></td>
                <td className="px-3 py-3 text-xs">{c.send_at ? stampMYT(c.send_at) : "—"}</td>
                <td className="px-3 py-3"><span className={`rounded-pill px-2 py-0.5 text-[11px] ${c.status === "sent" ? "bg-ok/10 text-ok" : c.status === "paused" ? "bg-warn/10 text-warn" : c.status === "draft" ? "bg-surface-2 text-muted" : "bg-accent/10 text-accent"}`}>{w(STATUS_WORDS, c.status)}</span></td>
                <td className="px-3 py-3 text-xs tabular-nums">{c.sent_count}{c.error_count ? <span className="text-danger"> · {c.error_count} {t("gagal", "failed")}</span> : null}{pending ? <span className="text-muted"> · {pending} {t("menunggu", "waiting")}</span> : null}</td>
                <td className="px-3 py-3"><div className="flex justify-end gap-1">
                  {c.channel === "whatsapp" && c.status !== "draft" && <Button size="sm" variant="ghost" onClick={() => onBoard(c)}><MessageCircle size={13} /> {t("Papan blast", "Blast board")}</Button>}
                  {["scheduled", "sending"].includes(c.status) && <Button size="sm" variant="ghost" onClick={() => onStatus(c, "paused")}>{t("Jeda", "Pause")}</Button>}
                  {c.status === "paused" && <Button size="sm" variant="ghost" onClick={() => onStatus(c, c.kind === "welcome" ? "scheduled" : "sending")}>{t("Sambung", "Resume")}</Button>}
                  <Button size="sm" variant="ghost" onClick={() => onEdit(c)} title={t("Sunting", "Edit")}><Pencil size={13} /></Button>
                  <Button size="sm" variant="ghost" disabled={c.status === "deleting"} onClick={() => onDelete(c)} title={t("Padam", "Delete")}><Trash2 size={13} /></Button>
                </div></td>
              </tr>
            );
          })}
          {!campaigns.length && <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted">{t("Tiada kempen. Tekan Kempen untuk menulis satu.", "No campaigns. Press Campaign to write one.")}</td></tr>}
        </tbody>
      </table>
      <p className="px-4 py-3 text-[11px] text-muted"><AlertTriangle size={11} className="mr-1 inline" />{t("Had: {d} e-mel sehari dari peti mel, {r} setiap larian pekerja (Tetapan → crm). Kempen yang dijeda tidak menghantar apa-apa sehingga disambung.",
        "Caps: {d} e-mails a day from the mailbox, {r} per worker run (Settings → crm). A paused campaign sends nothing until resumed.", { d: 200, r: 60 })}</p>
    </Card>
  );
}

function CampaignComposer({ form, setForm, contacts, allTags, busy, testTo, t, w, onSave, onTest, onQueue }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e?.target ? e.target.value : e });
  const aud = audienceOf(form, contacts);
  const sample = aud.send[0] || contacts[0] || { name: "Aisyah", company: "Marosia Maison" };
  const toggle = (key, v) => { const cur = form.audience?.[key] || []; setForm({ ...form, audience: { ...form.audience, [key]: cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v] } }); };
  const locked = form.status === "sent" || form.status === "deleting";
  const wa = form.channel === "whatsapp";
  return (
    <div className="space-y-3">
      <Segmented value={form.channel || "email"} onChange={(v) => setForm({ ...form, channel: v })} options={[["email", "E-mel"], ["whatsapp", "WhatsApp"]]} />
      <div className="grid gap-3 sm:grid-cols-2">
        <label><Label>{t("Nama kempen", "Campaign name")}</Label><Input value={form.name} onChange={set("name")} placeholder={t("Promo Notifikasi Oktober", "October notification promo")} /></label>
        <label><Label>{t("Jenis", "Kind")}</Label><Select className="w-full" value={form.kind} onChange={set("kind")} options={[["broadcast", t("Siaran sekali pada masa yang ditetapkan", "Broadcast once at a set time")], ["welcome", t("Alu-aluan: automatik kepada setiap kenalan baharu yang bersetuju", "Welcome: automatic to every new consenting contact")]]} /></label>
      </div>
      {!wa && <label className="block"><Label>{t("Subjek", "Subject")} <span className="font-normal opacity-70">{"{{name}} {{company}}"}</span></Label><Input value={form.subject} onChange={set("subject")} /></label>}
      <label className="block"><Label>{wa ? t("Mesej (teks biasa; {{name}} {{company}} diisi; had 4,000 aksara)", "Message (plain text; {{name}} {{company}} filled in; 4,000 characters at most)") : t("Kandungan (teks atau HTML; perenggan dipisah baris kosong)", "Body (text or HTML; paragraphs separated by a blank line)")}</Label><TextArea rows={8} value={form.body} onChange={set("body")} /></label>
      <div className="rounded-tile border border-line bg-surface-2/60 p-3 text-sm">
        <p className="mb-1 text-[11px] uppercase tracking-widest text-muted">{t("Pratonton untuk {n}", "Preview for {n}", { n: sample.name })}</p>
        {!wa && <p className="font-medium">{merge(form.subject, sample) || "—"}</p>}
        <div className="prose prose-sm mt-1 max-w-none text-ink/90" dangerouslySetInnerHTML={{ __html: /<[a-z][^>]*>/i.test(form.body) ? merge(form.body, sample) : merge(form.body, sample).split(/\n\s*\n/).map((p) => `<p>${p.replace(/</g, "&lt;").replace(/\n/g, "<br>")}</p>`).join("") }} />
        <p className="mt-2 border-t border-line pt-2 text-[11px] text-muted">{wa ? t("+ baris 'Balas STOP' dan pautan berhenti melanggan di bawah setiap mesej. Meta hanya membenarkan teks bebas dalam 24 jam selepas orang itu menulis kepada anda; di luar itu API menolak dan papan blast (klik satu persatu) adalah jalannya.", "+ a 'Reply STOP' line and the unsubscribe link under every message. Meta allows free text only within 24 hours of the person writing to you; outside that the API refuses and the blast board (click one by one) is the way.")
          : t("+ nota PDPA dan pautan berhenti melanggan ditambah oleh pekerja di bawah setiap e-mel.", "+ the PDPA line and the unsubscribe link, added by the worker under every e-mail.")}</p>
      </div>
      <div className="rounded-tile border border-line p-3">
        <p className="mb-2 text-[11px] uppercase tracking-widest text-muted">{t("Penerima", "Audience")} · <span className="normal-case tracking-normal">{t("{n} akan menerima daripada {m} yang dinamakan", "{n} will receive of {m} named", { n: aud.send.length, m: aud.named.length })}</span></p>
        <div className="flex flex-wrap gap-1">{STAGES.map((s) => <button type="button" key={s} onClick={() => toggle("stages", s)} className={`rounded-pill px-3 py-1 text-xs ${(form.audience?.stages || []).includes(s) ? "bg-ink text-surface" : "bg-surface-2 text-muted"}`}>{w(STAGE_WORDS, s)}</button>)}</div>
        {allTags.length ? <div className="mt-2 flex flex-wrap gap-1">{allTags.map((x) => <button type="button" key={x} onClick={() => toggle("tags", x)} className={`rounded-pill px-3 py-1 text-xs ${(form.audience?.tags || []).includes(x) ? "bg-ink text-surface" : "bg-surface-2 text-muted"}`}>#{x}</button>)}</div> : null}
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
          <Select value={form.audience?.lang || ""} onChange={(v) => setForm({ ...form, audience: { ...form.audience, lang: v } })} options={[["", t("Kedua-dua bahasa", "Both languages")], ["bm", "Bahasa Malaysia"], ["en", "English"]]} />
          {aud.skipped.length ? <span className="text-muted">{t("{n} dilangkau: {c} tanpa kebenaran, {u} berhenti melanggan, {e} tanpa {w}", "{n} skipped: {c} no consent, {u} unsubscribed, {e} no {w}",
            { n: aud.skipped.length, c: aud.skipped.filter((k) => k.why === "no_consent").length, u: aud.skipped.filter((k) => k.why === "unsubscribed").length,
              e: aud.skipped.filter((k) => k.why === "no_email" || k.why === "no_phone").length, w: wa ? t("nombor", "number") : t("e-mel", "e-mail") })}</span> : null}
        </div>
      </div>
      {form.kind === "broadcast" && <label className="block"><Label>{t("Hantar pada (MYT; kosong = sebaik sahaja pekerja bangun)", "Send at (MYT; blank = as soon as the worker wakes)")}</Label>
        <Input type="datetime-local" value={form.send_at ? (form.send_at.length === 16 ? form.send_at : toLocalInput(form.send_at)) : ""} onChange={(e) => setForm({ ...form, send_at: e.target.value })} /></label>}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" disabled={Boolean(busy)} onClick={onSave}>{t("Simpan draf", "Save draft")}</Button>
        {!wa && <Button variant="ghost" disabled={Boolean(busy)} onClick={onTest} title={testTo}><Mail size={13} /> {t("Hantar ujian kepada saya", "Send a test to me")}</Button>}
        <Button disabled={Boolean(busy) || locked} onClick={() => { if (window.confirm(t("Giliran e-mel ini kepada {n} kenalan? Pekerja menghantar pada masa yang ditetapkan dan ia tidak boleh ditarik balik selepas dihantar.", "Queue this e-mail to {n} contacts? The worker sends at the set time and a sent e-mail cannot be recalled.", { n: aud.send.length }))) onQueue(); }}>
          <Send size={13} /> {form.kind === "welcome" ? t("Aktifkan", "Activate") : form.send_at ? t("Jadualkan", "Schedule") : t("Hantar", "Send")}</Button>
      </div>
      {locked ? <p className="text-xs text-muted">{t("Kempen ini sudah dihantar; mesej yang sudah keluar tidak berubah.", "This campaign has gone; messages already out do not change.")}</p>
        : form.id && ["scheduled", "sending", "paused"].includes(form.status) ? <p className="text-xs text-muted">{t("Simpan mengemas kini setiap mesej yang masih menunggu; yang sudah dihantar kekal.", "Save updates every message still waiting; those already sent stay as they went.")}</p> : null}
    </div>
  );
}

/* The blast board: a WhatsApp campaign with no API sender. One row per queued contact, a wa.me link carrying the words,
   and "Sent" once Wan has pressed send in WhatsApp — the row is then counted like any other. */
function BlastBoard({ rows, contacts, t, onSent, waApi }) {
  const nameOf = (id) => contacts.find((k) => k.id === id);
  const pending = rows.filter((o) => o.status === "pending");
  const done = rows.filter((o) => o.status !== "pending");
  return (
    <div className="space-y-3 text-sm">
      <p className="text-xs text-muted">{waApi ? t("API disambung: pekerja menghantar baris ini sendiri. Papan ini untuk menghantar lebih awal dengan tangan.", "API connected: the worker sends these itself. This board is for sending by hand ahead of it.")
        : t("Tekan Buka: WhatsApp dibuka dengan mesej sedia diisi. Tekan hantar di sana, kembali, dan tekan Dihantar.", "Press Open: WhatsApp opens with the message filled in. Press send there, come back, and press Sent.")}</p>
      <ol className="max-h-96 space-y-2 overflow-y-auto">
        {pending.map((o) => {
          const k = nameOf(o.contact_id);
          return (
            <li key={o.id} className="flex items-center justify-between gap-2 rounded-tile border border-line p-2">
              <div className="min-w-0"><p className="truncate font-medium">{k?.name || o.to_phone}</p><p className="truncate text-xs text-muted">+{o.to_phone} · {o.body.slice(0, 70)}</p></div>
              <div className="flex shrink-0 gap-1">
                <a href={waLink(o.to_phone, o.body)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-pill bg-ok/10 px-3 py-1.5 text-xs text-ok"><ExternalLink size={12} /> {t("Buka", "Open")}</a>
                <Button size="sm" variant="ghost" onClick={() => onSent(o)}>{t("Dihantar", "Sent")}</Button>
              </div>
            </li>
          );
        })}
        {!pending.length && <li className="text-xs text-muted">{t("Tiada yang menunggu.", "Nothing waiting.")}</li>}
      </ol>
      {done.length ? <p className="text-xs text-muted">{t("{n} sudah dihantar / dilangkau.", "{n} already sent / skipped.", { n: done.length })}</p> : null}
    </div>
  );
}

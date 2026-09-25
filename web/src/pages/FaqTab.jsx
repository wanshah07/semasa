import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Bot, Check, Clock, FileDown, FileSpreadsheet, Image as ImageIcon, Inbox, Loader2, Pencil, Plus,
  RotateCcw, Search, Sparkles, Trash2, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { aOf, download, exportExcel, exportPdf, exportPoster, faqCategories, fileName, posterCard, qOf } from "../lib/faqExport";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Modal, Segmented, Select, TextArea } from "../components/ui/Field";

const WORKER_URL = "https://github.com/wanshah07/semasa/actions/workflows/media.yml";
const norm = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "");

/** Words in any field of a ready entry, for the search bar. */
function haystack(r) {
  return norm([r.question_bm, r.answer_bm, r.question_en, r.answer_en, r.subcategory, r.instrument,
    ...(r.tags || [])].join(" "));
}

export default function FaqTab({ faqs, settings, brand, user, onToast }) {
  const { t, lang } = useLang();
  const cats = useMemo(() => faqCategories(settings), [settings]);
  const catBy = useMemo(() => Object.fromEntries(cats.map((c) => [c.key, c])), [cats]);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState("all");
  const [sub, setSub] = useState("");
  // the content view and the export follow the page language; each can still be flipped on its own afterwards
  const [view, setView] = useState(lang);
  const [exportLang, setExportLang] = useState(lang);
  useEffect(() => { setView(lang); setExportLang(lang); }, [lang]);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState("");
  const website = brand?.regulab?.website || "";

  const ready = faqs.rows.filter((r) => r.status === "ready");
  const candidates = faqs.rows.filter((r) => r.status === "candidate");
  const queue = faqs.rows.filter((r) => ["new", "working", "error"].includes(r.status));
  const words = norm(query).split(/\s+/).filter(Boolean);
  const matched = ready.filter((r) => !words.length || words.every((w) => haystack(r).includes(w)));
  const counts = {};
  for (const r of matched) counts[r.category] = (counts[r.category] || 0) + 1;
  const order = Object.fromEntries(cats.map((c, i) => [c.key, i]));
  const shown = matched.filter((r) => (cat === "all" || r.category === cat) && (!sub || r.subcategory === sub))
    .sort((a, b) => (order[a.category] ?? 99) - (order[b.category] ?? 99)
      || String(a.subcategory).localeCompare(String(b.subcategory)) || String(a.created_at).localeCompare(String(b.created_at)));
  const label = cat === "all" ? (view === "en" ? "All questions" : "Semua soalan")
    : `${(view === "en" ? catBy[cat]?.en : catBy[cat]?.bm) || cat}${sub ? ` · ${sub}` : ""}`;
  const labelFor = (lang) => (cat === "all" ? (lang === "en" ? "All questions" : "Semua soalan")
    : `${(lang === "en" ? catBy[cat]?.en : catBy[cat]?.bm) || cat}${sub ? ` · ${sub}` : ""}`);

  async function update(ids, patch, msg) {
    const { error } = await supabase.from(TABLES.faqs).update(patch).in("id", ids);
    if (error) return onToast(errText(error), "danger");
    if (msg) onToast(msg, "ok");
    faqs.reload();
  }
  async function remove(id) {
    if (!window.confirm(t("Padam soalan ini? Ia juga hilang daripada Google Sheet pada larian seterusnya.", "Delete this question? It also disappears from the Google Sheet on the next run."))) return;
    const { error } = await supabase.from(TABLES.faqs).delete().eq("id", id);
    if (error) onToast(errText(error), "danger"); else { onToast(t("Dipadam.", "Deleted."), "info"); faqs.reload(); }
  }
  async function run(kind, fn) {
    setBusy(kind);
    try { await fn(); } catch (e) { onToast(e.message || String(e), "danger"); } finally { setBusy(""); }
  }

  const exportLangOptions = [["bm", "BM"], ["en", "EN"], ["both", "BM + EN"]];
  const posterLang = exportLang === "both" ? "bm" : exportLang;

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">FAQ</p>
          <h1 className="mt-2 text-4xl leading-tight">{t("Soalan lazim, satu tempat.", "Frequently asked questions, in one place.")}</h1>
          <p className="mt-3 max-w-2xl text-sm text-muted">
            {lang === "en" ? (<>
              Paste your own questions (and answers), press <b>Make an FAQ</b> on an issue, or accept candidates the bot has gathered.
              The AI rewrites them in BM and English, removes names and personal details, and picks a category. Every
              question is copied to the Semasa Google Sheet, and every category can be exported as a PDF, poster or Excel file.
            </>) : (<>
              Tampal soalan (dan jawapan) sendiri, tekan <b>Jadikan FAQ</b> pada isu, atau terima calon yang dikumpul bot.
              AI menulis semula dalam BM dan English, membuang nama dan maklumat peribadi, dan memilih kategori. Setiap
              soalan disalin ke Google Sheet Semasa, dan setiap kategori boleh dieksport sebagai PDF, poster atau Excel.
            </>)}
          </p>
        </div>
        <Button onClick={() => setAdding(true)}><Plus size={14} /> {t("Tambah FAQ", "Add FAQ")}</Button>
      </motion.div>

      {faqs.error && (
        <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">
          {/semasa_faqs/.test(faqs.error) ? t("FAQ belum disediakan dalam pangkalan data: jalankan supabase/007_faq.sql sekali di Supabase SQL editor.", "The FAQ is not set up in the database yet: run supabase/007_faq.sql once in the Supabase SQL editor.") : faqs.error}
        </p>
      )}

      <div className="z-30 sm:sticky sm:top-[97px] xl:top-[65px] -mx-4 mt-6 bg-bg/85 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-0 flex-1 basis-60">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <Input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("Cari soalan, jawapan, tag…", "Search questions, answers, tags…")}
              className="pl-9" aria-label={t("Cari FAQ", "Search FAQ")} />
          </label>
          <Segmented value={view} onChange={setView} options={[["bm", "BM"], ["en", "EN"]]} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs" role="tablist" aria-label={t("Kategori", "Categories")}>
          <button type="button" role="tab" aria-selected={cat === "all"} onClick={() => { setCat("all"); setSub(""); }}
            className={`rounded-pill px-3 py-1.5 ${cat === "all" ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
            {view === "en" ? "All" : "Semua"} · {matched.length}</button>
          {cats.map((c) => (
            <button type="button" role="tab" key={c.key} aria-selected={cat === c.key} onClick={() => { setCat(c.key); setSub(""); }}
              className={`rounded-pill px-3 py-1.5 ${cat === c.key ? "bg-ink text-bg" : "bg-surface-2 text-muted"} ${counts[c.key] ? "" : "opacity-60"}`}>
              {view === "en" ? c.en : c.bm} · {counts[c.key] || 0}</button>
          ))}
        </div>
        {cat !== "all" && (catBy[cat]?.subs || []).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
            {["", ...catBy[cat].subs].map((s) => (
              <button type="button" key={s || "_all"} onClick={() => setSub(s)}
                className={`rounded-pill border px-2.5 py-1 ${sub === s ? "border-accent text-accent" : "border-line text-muted"}`}>
                {s || (view === "en" ? "All" : "Semua")}</button>
            ))}
          </div>
        )}
      </div>

      <Card className="mt-3 flex flex-wrap items-center gap-2 p-3">
        <span className="mr-auto text-sm"><b>{label}</b> <span className="text-muted">· {t("{n} soalan untuk dieksport", ["{n} question to export", "{n} questions to export"], { n: shown.length })}</span></span>
        <Select value={exportLang} onChange={setExportLang} options={exportLangOptions} aria-label={t("Bahasa eksport", "Export language")} />
        <Button size="sm" variant="soft" disabled={!shown.length || !!busy} onClick={() => run("pdf", async () =>
          exportPdf(shown, { label: labelFor(exportLang === "en" ? "en" : "bm"), lang: exportLang, website, cats }))}>
          <FileDown size={12} /> PDF</Button>
        <Button size="sm" variant="soft" disabled={!shown.length || !!busy} title={exportLang === "both" ? t("Poster dibuat dalam BM", "The poster is made in BM") : ""}
          onClick={() => run("poster", async () => {
            await exportPoster(shown, { lang: posterLang, label: labelFor(posterLang), website });
            onToast(t("Poster dimuat turun.", "Poster downloaded."), "ok");
          })}>
          {busy === "poster" ? <Loader2 size={12} className="animate-spin" /> : <ImageIcon size={12} />} Poster</Button>
        <Button size="sm" variant="soft" disabled={!shown.length || !!busy} onClick={() => run("excel", async () => {
          await exportExcel(shown, cats, labelFor("bm"));
          onToast(t("Excel dimuat turun.", "Excel file downloaded."), "ok");
        })}>
          {busy === "excel" ? <Loader2 size={12} className="animate-spin" /> : <FileSpreadsheet size={12} />} Excel</Button>
      </Card>

      {candidates.length > 0 && (
        <details className="mt-4 rounded-card border border-line bg-surface p-3">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <Inbox size={14} /> {t("Calon daripada sumber", "Candidates from sources")} · {candidates.length}
            <span className="text-[11px] font-normal text-muted">{t("dikumpul oleh bot; tiada apa ditulis semula sehingga anda terima", "gathered by the bot; nothing is rewritten until you accept")}</span>
          </summary>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={() => update(candidates.map((r) => r.id), { status: "new" }, t("{n} calon dihantar ke AI.", ["{n} candidate sent to the AI.", "{n} candidates sent to the AI."], { n: candidates.length }))}>
              <Check size={12} /> {t("Terima semua", "Accept all")}</Button>
            <Button size="sm" variant="ghost" onClick={() => update(candidates.map((r) => r.id), { status: "dismissed" }, t("Semua calon diabaikan.", "All candidates dismissed."))}>
              {t("Abaikan semua", "Dismiss all")}</Button>
          </div>
          <ul className="mt-3 space-y-2">
            {candidates.map((r) => (
              <li key={r.id} className="rounded-tile bg-surface-2/60 p-2.5 text-sm">
                <p className="text-[11px] text-muted">{r.source_name}{r.raw_answer ? t(" · ada jawapan", " · has an answer") : t(" · soalan sahaja: AI akan menjawab dan menandanya perlu semakan", " · question only: the AI will answer it and mark it needs check")}</p>
                <p className="mt-1 line-clamp-3 font-medium">{r.raw_question}</p>
                {r.raw_answer && <p className="mt-1 line-clamp-2 text-[12px] text-muted">{r.raw_answer}</p>}
                <div className="mt-2 flex flex-wrap gap-2">
                  <Button size="sm" variant="soft" onClick={() => update([r.id], { status: "new" }, t("Dihantar ke AI.", "Sent to the AI."))}><Check size={12} /> {t("Terima", "Accept")}</Button>
                  <Button size="sm" variant="ghost" onClick={() => update([r.id], { status: "dismissed" }, t("Diabaikan.", "Dismissed."))}>{t("Abaikan", "Dismiss")}</Button>
                  {r.source_url && <a href={r.source_url} target="_blank" rel="noopener noreferrer" className="self-center text-[11px] text-accent underline">{t("sumber", "source")}</a>}
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}

      {queue.length > 0 && (
        <div className="mt-4 space-y-2">
          {queue.map((r) => {
            const late = r.status === "new" && Date.now() - new Date(r.updated_at || r.created_at).getTime() > 20 * 60_000;
            return (
              <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-tile border border-line bg-surface px-3 py-2 text-[12px]">
                {r.status === "working" ? <Loader2 size={12} className="animate-spin text-accent" />
                  : r.status === "error" ? <AlertTriangle size={12} className="text-danger" /> : <Clock size={12} className="text-warn" />}
                <span className="min-w-0 flex-1 truncate">{r.raw_question}</span>
                <span className="text-muted">{r.status === "working" ? t("AI sedang menulis", "AI is writing") : r.status === "error" ? t("Gagal", "Failed") : t("Menunggu bot", "Waiting for the bot")} · {timeAgo(r.created_at)}</span>
                {r.status === "error" && <Button size="sm" variant="soft" onClick={() => update([r.id], { status: "new", error: null }, t("Dihantar semula.", "Sent again."))}><RotateCcw size={11} /> {t("Cuba lagi", "Try again")}</Button>}
                {r.status !== "working" && <button type="button" aria-label={t("Padam", "Delete")} onClick={() => remove(r.id)} className="text-muted hover:text-danger"><Trash2 size={12} /></button>}
                {r.error && <p className="w-full break-words text-danger">{r.error}</p>}
                {late && <p className="w-full text-ink">{t("Bot belum bermula: jadual GitHub kadang-kadang lewat. Mulakan di", "The bot has not started: GitHub's schedule is sometimes late. Start it at")}{" "}
                  <a href={WORKER_URL} target="_blank" rel="noopener noreferrer" className="font-medium text-accent underline">GitHub → Generate media → Run workflow</a>.</p>}
              </div>
            );
          })}
        </div>
      )}

      {cat === "all" && !words.length && ready.length > 0 && (
        <CategoryCards cats={cats} rows={ready} view={view} onPick={(k, s) => { setCat(k); setSub(s || ""); }} />
      )}

      <div className="mt-4 space-y-3">
        {!shown.length && !faqs.loading && (
          <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">
            {ready.length ? t("Tiada soalan sepadan dengan carian ini.", "No questions match this search.") : t("Belum ada FAQ. Tekan Tambah FAQ untuk tampal yang pertama.", "No FAQs yet. Press Add FAQ to paste the first one.")}</p>
        )}
        {shown.map((r) => (
          <Card key={r.id} as="article" className="p-4">
            <p className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
              <span className="rounded-pill bg-accent/10 px-2 py-0.5 text-accent">{(view === "en" ? catBy[r.category]?.en : catBy[r.category]?.bm) || r.category}</span>
              {r.subcategory && <span>{r.subcategory}</span>}
              {r.answer_source === "ai" && <span className="inline-flex items-center gap-1 rounded-pill bg-surface-2 px-2 py-0.5"><Bot size={10} /> {t("jawapan AI", "AI answer")}</span>}
              {r.needs_check && <span className="inline-flex items-center gap-1 rounded-pill bg-warn/10 px-2 py-0.5 text-warn" title={r.check_note}><AlertTriangle size={10} /> {t("perlu semakan", "needs check")}</span>}
              <span className="ml-auto">{timeAgo(r.updated_at || r.created_at)}</span>
            </p>
            <h3 className="mt-2 font-display text-[17px] leading-snug">{qOf(r, view)}</h3>
            <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink/90">{aOf(r, view)}</p>
            {r.instrument && <p className="mt-2 text-[11px] text-muted">{view === "en" ? "Source" : "Sumber"}: {r.instrument}</p>}
            {r.needs_check && r.check_note && <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px]">{r.check_note}</p>}
            {(r.tags || []).length > 0 && <p className="mt-2 flex flex-wrap gap-1">{r.tags.map((t) => (
              <button type="button" key={t} onClick={() => setQuery(t)} className="rounded-pill border border-line px-2 py-0.5 text-[10px] text-muted hover:text-ink">#{t}</button>))}</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" variant="ghost" onClick={() => setEditing(r)}><Pencil size={11} /> {t("Sunting", "Edit")}</Button>
              <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run(`card-${r.id}`, async () => {
                const lang = view;
                download(await posterCard(r, { lang, catLabel: (lang === "en" ? catBy[r.category]?.en : catBy[r.category]?.bm) || r.category, website }),
                  fileName(qOf(r, lang).slice(0, 40), "png", lang));
              })}>{busy === `card-${r.id}` ? <Loader2 size={11} className="animate-spin" /> : <ImageIcon size={11} />} {t("Kad", "Card")}</Button>
              <Button size="sm" variant="ghost" onClick={() => {
                if (window.confirm(t("Tulis semula daripada teks asal? Suntingan anda pada soalan ini akan diganti.", "Rewrite from the original text? Your edits to this question will be replaced."))) {
                  update([r.id], { status: "new", error: null }, t("Dihantar ke AI untuk ditulis semula.", "Sent to the AI to be rewritten."));
                }
              }}><RotateCcw size={11} /> {t("Tulis semula", "Rewrite")}</Button>
              <Button size="sm" variant="danger" onClick={() => remove(r.id)} aria-label={t("Padam soalan", "Delete question")}><Trash2 size={11} /></Button>
            </div>
          </Card>
        ))}
      </div>

      <AddFaq open={adding} onClose={() => setAdding(false)} cats={cats} user={user} onToast={onToast} onDone={faqs.reload} />
      {editing && <EditFaq row={editing} cats={cats} onClose={() => setEditing(null)} onToast={onToast} onDone={faqs.reload} />}
    </main>
  );
}

/* Manual entry: paste a question and (if there is one) its answer, exactly as it arrived. */
function AddFaq({ open, onClose, cats, user, onToast, onDone }) {
  const { t, lang } = useLang();
  const [q, setQ] = useState("");
  const [a, setA] = useState("");
  const [url, setUrl] = useState("");
  const [cat, setCat] = useState("lain");
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    if (!q.trim()) return onToast(t("Tampal soalannya dahulu.", "Paste the question first."), "warn");
    setBusy(true);
    const { error } = await supabase.from(TABLES.faqs).insert({
      status: "new", source_kind: "paste", raw_question: q.trim(), raw_answer: a.trim(), source_url: url.trim() || null,
      category: cat, category_by: cat === "lain" ? "bot" : "wan", created_by: user.id,
    });
    setBusy(false);
    if (error) return onToast(/semasa_faqs/.test(errText(error)) ? t("Jalankan supabase/007_faq.sql dahulu.", "Run supabase/007_faq.sql first.") : errText(error), "danger");
    onToast(t("Dihantar. AI akan tulis semula dalam BM dan English.", "Sent. The AI will rewrite it in BM and English."), "ok");
    setQ(""); setA(""); setUrl(""); setCat("lain");
    onDone?.(); onClose();
  }
  return (
    <Modal open={open} onClose={onClose} title={t("Tambah FAQ", "Add FAQ")}>
      <form onSubmit={submit} className="space-y-3">
        <label className="block"><Label hint={t("tampal seperti diterima; nama dan maklumat peribadi akan dibuang", "paste it as received; names and personal details will be removed")}>{t("Soalan", "Question")}</Label>
          <TextArea rows={5} value={q} onChange={(e) => setQ(e.target.value)} required maxLength={6000}
            placeholder={t("Cth: Salam, saya ada soalan berkenaan sijil halal…", "E.g. Hello, I have a question about halal certification…")} /></label>
        <label className="block"><Label hint={t("pilihan; kosong = AI menjawab dan menandanya perlu semakan", "optional; empty = the AI answers and marks it needs check")}>{t("Jawapan", "Answer")}</Label>
          <TextArea rows={4} value={a} onChange={(e) => setA(e.target.value)} maxLength={6000} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><Label hint={t("kosong = AI pilih", "empty = the AI chooses")}>{t("Kategori", "Category")}</Label>
            <Select value={cat} onChange={setCat} options={[["lain", t("AI pilih", "AI chooses")], ...cats.filter((c) => c.key !== "lain").map((c) => [c.key, lang === "en" ? c.en : c.bm])]} className="w-full" aria-label={t("Kategori", "Category")} /></label>
          <label className="block"><Label hint={t("pilihan", "optional")}>{t("Pautan sumber", "Source link")}</Label>
            <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></label>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>{t("Batal", "Cancel")}</Button>
          <Button type="submit" disabled={busy}>{busy ? t("Menghantar…", "Sending…") : t("Hantar ke AI", "Send to the AI")}</Button>
        </div>
      </form>
    </Modal>
  );
}

/* The dashboard: one card per category with what is in it, the bot's own categories marked. A category with
   nothing in it yet is left out, except the bot's newest, so a category it just opened is visible at once. */
function CategoryCards({ cats, rows, view, onPick }) {
  const { t } = useLang();
  const stats = {};
  for (const r of rows) {
    const s = (stats[r.category] ||= { n: 0, check: 0, subs: {}, last: "" });
    s.n += 1;
    if (r.needs_check) s.check += 1;
    if (r.subcategory) s.subs[r.subcategory] = (s.subs[r.subcategory] || 0) + 1;
    const at = r.updated_at || r.created_at || "";
    if (at > s.last) s.last = at;
  }
  const known = new Set(cats.map((c) => c.key));
  const orphans = Object.keys(stats).filter((k) => !known.has(k));
  const list = [...cats.filter((c) => stats[c.key] || c.auto),
    ...orphans.map((k) => ({ key: k, bm: k, en: k, subs: [], gone: true }))];
  return (
    <section className="mt-4" aria-label={t("Kategori", "Categories")}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((c) => {
          const s = stats[c.key] || { n: 0, check: 0, subs: {}, last: "" };
          const top = Object.entries(s.subs).sort((a, b) => b[1] - a[1]).slice(0, 3);
          const autoSubs = new Set(c.auto_subs || []);
          return (
            <button type="button" key={c.key} onClick={() => onPick(c.key)} data-cat={c.key}
              className="group rounded-card border border-line bg-surface p-4 text-left transition hover:border-accent/60 hover:shadow-sm">
              <span className="flex items-start gap-2">
                <span className="min-w-0 flex-1">
                  <span className="block font-display text-lg leading-tight group-hover:text-accent">{view === "en" ? c.en : c.bm}</span>
                  <span className="mt-0.5 block text-[11px] text-muted">{view === "en" ? c.bm : c.en}</span>
                </span>
                <span className="font-display text-2xl tabular-nums">{s.n}</span>
              </span>
              <span className="mt-2 flex flex-wrap gap-1.5 text-[10px]">
                {c.auto && <span className="inline-flex items-center gap-1 rounded-pill bg-accent/10 px-2 py-0.5 text-accent"><Sparkles size={10} /> {t("dicipta bot", "made by the bot")}</span>}
                {c.gone && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-warn">{t("kategori dipadam: bot akan menyusun semula", "category deleted: the bot will re-sort it")}</span>}
                {s.check > 0 && <span className="inline-flex items-center gap-1 rounded-pill bg-warn/10 px-2 py-0.5 text-warn"><AlertTriangle size={10} /> {t("{n} perlu semakan", "{n} to check", { n: s.check })}</span>}
                {!s.n && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-muted">{t("belum ada soalan", "no questions yet")}</span>}
              </span>
              {top.length > 0 && (
                <span className="mt-3 flex flex-wrap gap-1">
                  {top.map(([name, n]) => (
                    <span key={name} className="rounded-pill border border-line px-2 py-0.5 text-[10px] text-muted">
                      {name} · {n}{autoSubs.has(name) ? " ✦" : ""}</span>
                  ))}
                </span>
              )}
              {s.last && <span className="mt-2 block text-[10px] text-muted">{t("dikemas kini {ago}", "updated {ago}", { ago: timeAgo(s.last) })}</span>}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function EditFaq({ row, cats, onClose, onToast, onDone }) {
  const { t, lang } = useLang();
  const [f, setF] = useState({
    question_bm: row.question_bm, answer_bm: row.answer_bm, question_en: row.question_en, answer_en: row.answer_en,
    category: row.category, subcategory: row.subcategory || "", instrument: row.instrument || "",
    needs_check: !!row.needs_check, check_note: row.check_note || "", tags: (row.tags || []).join(", "),
  });
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e }));
  const subs = cats.find((c) => c.key === f.category)?.subs || [];
  async function save() {
    const patch = { ...f, subcategory: f.subcategory === (row.subcategory || "") || subs.includes(f.subcategory) ? f.subcategory : "",
      tags: f.tags.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean).slice(0, 5),
      check_note: f.needs_check ? f.check_note : "", status: "ready" };
    // a category chosen by hand stays put: the bot neither rewrites nor re-sorts it
    if (f.category !== row.category || f.subcategory !== (row.subcategory || "")) patch.category_by = "wan";
    const { error } = await supabase.from(TABLES.faqs).update(patch).eq("id", row.id);
    if (error) return onToast(errText(error), "danger");
    onToast(t("Disimpan.", "Saved."), "ok"); onDone?.(); onClose();
  }
  return (
    <Modal open onClose={onClose} title={t("Sunting FAQ", "Edit FAQ")}>
      <div className="space-y-3">
        <label className="block"><Label>{t("Soalan (BM)", "Question (BM)")}</Label><TextArea rows={2} value={f.question_bm} onChange={set("question_bm")} /></label>
        <label className="block"><Label>{t("Jawapan (BM)", "Answer (BM)")}</Label><TextArea rows={4} value={f.answer_bm} onChange={set("answer_bm")} /></label>
        <label className="block"><Label>Question (EN)</Label><TextArea rows={2} value={f.question_en} onChange={set("question_en")} /></label>
        <label className="block"><Label>Answer (EN)</Label><TextArea rows={4} value={f.answer_en} onChange={set("answer_en")} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><Label>{t("Kategori", "Category")}</Label>
            <Select value={f.category} onChange={(v) => setF((x) => ({ ...x, category: v, subcategory: "" }))} options={cats.map((c) => [c.key, lang === "en" ? c.en : c.bm])} className="w-full" aria-label={t("Kategori", "Category")} /></label>
          <label className="block"><Label>{t("Subkategori", "Subcategory")}</Label>
            <Select value={f.subcategory} onChange={set("subcategory")} options={[["", "—"], ...subs.map((s) => [s, s]), ...(f.subcategory && !subs.includes(f.subcategory) ? [[f.subcategory, f.subcategory]] : [])]} className="w-full" aria-label={t("Subkategori", "Subcategory")} /></label>
        </div>
        <label className="block"><Label hint={t("pengawal selia / instrumen sahaja, bukan media sosial", "regulator / instrument only, not social media")}>{t("Sumber rasmi", "Official source")}</Label><Input value={f.instrument} onChange={set("instrument")} /></label>
        <label className="block"><Label hint={t("dipisah dengan koma, maksimum 5", "comma-separated, up to 5")}>{t("Tag", "Tags")}</Label><Input value={f.tags} onChange={set("tags")} /></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.needs_check} onChange={set("needs_check")} /> {t("Perlu semakan", "Needs check")}</label>
        {f.needs_check && <Input value={f.check_note} onChange={set("check_note")} placeholder={t("Apa yang perlu disemak", "What needs checking")} />}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}><X size={12} /> {t("Batal", "Cancel")}</Button>
          <Button type="button" onClick={save}><Check size={12} /> {t("Simpan", "Save")}</Button>
        </div>
      </div>
    </Modal>
  );
}

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, ChevronDown, Cpu, Download, ExternalLink, FileText, HelpCircle, Info, Lightbulb, Radio, Search,
  Send, Settings, Sparkles, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { download } from "../lib/faqExport";
import { currentLang, tr, useLang } from "../lib/i18n";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Segmented, Select } from "../components/ui/Field";

/* The log, as the database writes it (supabase/008_log.sql): every row the same shape, written by a
   trigger at the moment something changes, never by hand. This page only reads and sorts it. */

export const AREAS = {
  scrape: { label: "Scrape", en: "Scrape", icon: Radio }, idea: { label: "Idea", en: "Ideas", icon: Lightbulb },
  post: { label: "Post", en: "Posts", icon: FileText }, media: { label: "Media", en: "Media", icon: Sparkles },
  faq: { label: "FAQ", en: "FAQ", icon: HelpCircle }, publish: { label: "Penerbit", en: "Publisher", icon: Send },
  settings: { label: "Tetapan", en: "Settings", icon: Settings }, system: { label: "Sistem", en: "System", icon: Cpu },
};
const areaLabel = (a) => (currentLang() === "en" ? a.en : a.label);
const LEVEL = {
  info: { icon: Info, cls: "text-muted", dot: "bg-line" },
  warn: { icon: AlertTriangle, cls: "text-warn", dot: "bg-warn" },
  error: { icon: XCircle, cls: "text-danger", dot: "bg-danger" },
};
const LABELS_EN = {
  seen: "Read", inserted: "New", llm_ok: "AI used", llm_model: "AI model", failed_sources: "Failed sources", note: "Note",
  seconds: "Duration (s)", stream: "Stream", domain: "Domain", media: "Media", error: "Error", attempts: "Attempts",
  provider: "Provider", model: "Model", slides: "Slides", category: "Category", subcategory: "Subcategory",
  answer_source: "Answered by", check_note: "Check note", channel: "Channel", why: "Reason", due_at: "Send time",
  date: "Date", slot: "Slot", from_date: "From date", from_slot: "From slot", key: "Setting", source: "Source",
  new: "New", dropped: "Dropped", pick_hours: "Limit (hours)", rows: "Rows", read_article: "Article read",
  hard_flags: "Blocks", mode: "Mode", type: "Type", status: "Status", moved: "Moved", new_categories: "New categories",
  looked_at: "Looked at", added: "Added", event: "Event",
};
const LABELS = {
  seen: "Dibaca", inserted: "Baharu", llm_ok: "AI digunakan", llm_model: "Model AI", failed_sources: "Sumber gagal", note: "Nota",
  seconds: "Tempoh (saat)", stream: "Aliran", domain: "Domain", media: "Media", error: "Ralat", attempts: "Cubaan",
  provider: "Penyedia", model: "Model", slides: "Slaid", category: "Kategori", subcategory: "Subkategori",
  answer_source: "Jawapan oleh", check_note: "Nota semakan", channel: "Saluran", why: "Sebab", due_at: "Masa hantar",
  date: "Tarikh", slot: "Slot", from_date: "Dari tarikh", from_slot: "Dari slot", key: "Tetapan", source: "Sumber",
  new: "Baharu", dropped: "Dibuang", pick_hours: "Had (jam)", rows: "Baris", read_article: "Artikel dibaca",
  hard_flags: "Sekatan", mode: "Mod", type: "Jenis", status: "Status", moved: "Dialih", new_categories: "Kategori baharu",
  looked_at: "Disemak", added: "Ditambah", event: "Peristiwa",
};
const labelOf = (k) => (currentLang() === "en" ? LABELS_EN[k] : LABELS[k]) || k;

/* The database writes titles in Malay (008_log.sql, and a few from the worker). In English the fixed opening is
   translated and the rest (a headline, a question, a channel) is kept as written. Longest, most specific first. */
const TITLE_EN = [
  [/^Scrape selesai: (\d+) baharu daripada (\d+) dibaca/, (m) => `Scrape finished: ${m[1]} new of ${m[2]} read`],
  [/^Scrape gagal: /, "Scrape failed: "],
  [/^(Scrape finished: .*?) · (\d+) sumber gagal/, (m) => `${m[1]} · ${m[2]} source${m[2] === "1" ? "" : "s"} failed`],
  [/^(Scrape finished: .*?) · AI tidak digunakan/, (m) => `${m[1]} · AI not used`],
  [/^(\d+) calon FAQ baharu daripada /, (m) => `${m[1]} new FAQ candidate${m[1] === "1" ? "" : "s"} from `],
  [/^(\d+) isu yang tidak dijadikan idea dibuang \(lebih (\d+) jam\)/, (m) => `${m[1]} issue${m[1] === "1" ? "" : "s"} not made into ideas dropped (older than ${m[2]} hours)`],
  [/^Idea baharu: /, "New idea: "], [/^Draf ditulis: /, "Draft written: "], [/^Idea gagal: /, "Idea failed: "],
  [/^Idea ditolak: /, "Idea rejected: "], [/^Idea dihantar semula: /, "Idea resent: "], [/^Idea dipadam: /, "Idea deleted: "],
  [/^Draf baharu: /, "New draft: "], [/^Post diluluskan: /, "Post approved: "], [/^Post ditolak: /, "Post rejected: "],
  [/^Kembali ke draf \(diubah selepas diluluskan\): /, "Back to draft (changed after approval): "],
  [/^Post dipulihkan ke draf: /, "Post restored to draft: "], [/^Dikembalikan ke draf: /, "Returned to draft: "], [/^Post dijadualkan: /, "Post scheduled: "],
  [/^Post diterbitkan: /, "Post published: "], [/^Post dialih: /, "Post moved: "], [/^Post dipadam: /, "Post deleted: "],
  [/^(\d+) post diarkibkan \(24 jam selepas diterbitkan\); (\d+) gambar tidak digunakan dibuang/,
    (m) => `${m[1]} post${m[1] === "1" ? "" : "s"} archived (24 hours after publishing); ${m[2]} unused picture${m[2] === "1" ? "" : "s"} removed`],
  [/^(Kerja media dibaris|Media siap|Media gagal) \((slaid|cipta semula|prompt) · /, (m) => `${
    { "Kerja media dibaris": "Media job queued", "Media siap": "Media ready", "Media gagal": "Media failed" }[m[1]]} (${
    { slaid: "slides", "cipta semula": "recreate", prompt: "prompt" }[m[2]]} · `],
  [/^FAQ daripada isu: /, "FAQ from an issue: "], [/^FAQ ditampal: /, "FAQ pasted: "],
  [/^Calon FAQ diterima: /, "FAQ candidate accepted: "], [/^Calon FAQ diabaikan: /, "FAQ candidate dismissed: "],
  [/^FAQ dihantar semula ke AI: /, "FAQ sent back to the AI: "], [/^FAQ siap: /, "FAQ ready: "],
  [/^(FAQ ready: .*) \(perlu semakan\)$/, (m) => `${m[1]} (needs check)`], [/^FAQ gagal: /, "FAQ failed: "], [/^FAQ disunting: /, "FAQ edited: "],
  [/^FAQ dipadam: /, "FAQ deleted: "],
  [/^Google Sheet dikemas kini: (\d+) soalan/, (m) => `Google Sheet updated: ${m[1]} question${m[1] === "1" ? "" : "s"}`],
  [/^Google Sheet gagal dikemas kini: /, "Google Sheet update failed: "],
  [/^Log gagal disalin ke Google Sheet: /, "Log could not be copied to the Google Sheet: "],
  [/^Bot menambah subkategori: /, "The bot added subcategories: "],
  [/^Susunan automatik FAQ gagal: AI tidak menjawab dengan betul; cuba semula dalam 3 jam/,
    "Automatic FAQ sorting failed: the AI did not answer properly; trying again in 3 hours"],
  [/^Bot menyusun (\d+) FAQ(?:: (.*?))?(?:; kategori baharu: (.*))?$/, (m) => `The bot sorted ${m[1]} FAQ${m[1] === "1" ? "" : "s"}${
    m[2] ? `: ${m[2].replace(/(^|, )(\d+) ke /g, "$1$2 to ")}` : ""}${m[3] ? `; new categories: ${m[3]}` : ""}`],
  [/^Cubaan kering: (\S+) akan menghantar /, (m) => `Dry run: ${m[1]} would send `], [/^Dihantar ke /, "Sent to "],
  [/^Disekat \(/, "Blocked ("], [/^Ralat penerbit \(/, "Publisher error ("],
  [/^Tetapan diubah: slot dan giliran/, "Settings changed: slots and rota"],
  [/^Tetapan diubah: kategori FAQ/, "Settings changed: FAQ categories"],
  [/^Tetapan diubah: tabung perkataan Indonesia/, "Settings changed: Indonesian word list"],
  [/^Tetapan diubah: suis penerbitan/, "Settings changed: publishing switch"],
  [/^Tetapan diubah: /, "Settings changed: "],
  [/^Jam Supabase: token GitHub tiada dalam Vault, jadi "([^"]+)" tidak dihantar \(README langkah 4\)/,
    (m) => `Supabase clock: no GitHub token in the Vault, so "${m[1]}" was not sent (README step 4)`],
  [/\(tanpa tajuk\)/, "(untitled)"],
];

/** A log title in the page's language. */
export function titleOf(title, lang = currentLang()) {
  let out = String(title || "");
  if (lang !== "en") return out;
  for (const [rx, to] of TITLE_EN) {
    out = typeof to === "string" ? out.replace(rx, to) : out.replace(rx, (...m) => to(m));
  }
  return out;
}

const RANGES = () => [["today", tr("Hari ini", "Today")], ["7", tr("7 hari", "7 days")], ["30", tr("30 hari", "30 days")],
  ["all", tr("Semua", "All")]];
const MYT_MS = 8 * 3600_000;

const mytDay = (iso) => new Date(new Date(iso).getTime() + MYT_MS).toISOString().slice(0, 10);
const locale = () => (currentLang() === "en" ? "en-GB" : "ms-MY");
const clock = (iso) => new Intl.DateTimeFormat(locale(), { timeZone: "Asia/Kuala_Lumpur", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
const dayTitle = (day) => new Intl.DateTimeFormat(locale(), { timeZone: "UTC", weekday: "long", day: "numeric", month: "long", year: "numeric" })
  .format(new Date(`${day}T00:00:00Z`));

function show(k, v) {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "boolean") return v ? tr("Ya", "Yes") : tr("Tidak", "No");
  if (k === "due_at") return `${new Intl.DateTimeFormat(locale(), { timeZone: "Asia/Kuala_Lumpur", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(v))} MYT`;
  if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : String(x))).join(" · ") : null;
  if (typeof v === "object") return Object.keys(v).length ? JSON.stringify(v) : null;
  return String(v);
}

/** Where an entry's open link goes: the tab, and the post to open when there is one. */
export function targetOf(r) {
  const postId = r.ref_table === "semasa_posts" ? r.ref_id : r.detail?.post_id;
  if (postId) return { tab: "post", postId };
  return { semasa_ideas: { tab: "idea" }, semasa_faqs: { tab: "faq" }, media_generations: { tab: "media" },
    scrape_runs: { tab: "isu" }, semasa_settings: { tab: "tetapan" } }[r.ref_table] || null;
}

export function toCsv(rows) {
  const q = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const head = currentLang() === "en" ? ["Time (MYT)", "Level", "Area", "Event", "Title", "By", "Reference", "Details"]
    : ["Masa (MYT)", "Tahap", "Bahagian", "Peristiwa", "Tajuk", "Oleh", "Rujukan", "Butiran"];
  const lines = rows.map((r) => [`${mytDay(r.at)} ${clock(r.at)}`, r.level, AREAS[r.area] ? areaLabel(AREAS[r.area]) : r.area,
    r.event, titleOf(r.title), r.actor ? tr("Anda", "You") : "Bot", r.ref_id || "", JSON.stringify(r.detail || {})].map(q).join(","));
  return "﻿" + [head.map(q).join(","), ...lines].join("\r\n");
}

export default function LogTab({ log, onOpen }) {
  const { t, lang } = useLang();
  const [range, setRange] = useState("7");
  const [area, setArea] = useState("all");
  const [level, setLevel] = useState("all");
  const [actor, setActor] = useState("all");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(null);

  const today = mytDay(new Date().toISOString());
  const inRange = useMemo(() => {
    if (range === "all") return log.rows;
    if (range === "today") return log.rows.filter((r) => mytDay(r.at) === today);
    const since = Date.now() - Number(range) * 86400_000;
    return log.rows.filter((r) => new Date(r.at).getTime() >= since);
  }, [log.rows, range, today]);

  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const byArea = {};
  const shown = inRange.filter((r) => {
    if (level === "warn" && r.level === "info") return false;
    if (level === "error" && r.level !== "error") return false;
    if (actor === "me" && !r.actor) return false;
    if (actor === "bot" && r.actor) return false;
    const hay = `${r.title} ${lang === "en" ? titleOf(r.title, "en") : ""} ${r.event} ${JSON.stringify(r.detail || {})}`.toLowerCase();
    if (words.length && !words.every((w) => hay.includes(w))) return false;
    byArea[r.area] = (byArea[r.area] || 0) + 1;
    return area === "all" || r.area === area;
  });

  const days = [];
  for (const r of shown) {
    const d = mytDay(r.at);
    const last = days[days.length - 1];
    if (last && last.day === d) last.rows.push(r); else days.push({ day: d, rows: [r] });
  }

  const todayRows = log.rows.filter((r) => mytDay(r.at) === today);
  const count = (fn) => todayRows.filter(fn).length;
  const scrapeBad = count((r) => r.event === "scrape.finished" && r.level !== "info");
  const tiles = [
    ["scrape", "Scrape", `${count((r) => r.event === "scrape.finished")}`,
      scrapeBad ? t("{n} bermasalah", "{n} with problems", { n: scrapeBad }) : t("semua lancar", "all fine")],
    ["drafted", t("Draf ditulis", "Drafts written"), `${count((r) => r.event === "idea.drafted")}`,
      t("{n} idea gagal", ["{n} idea failed", "{n} ideas failed"], { n: count((r) => r.event === "idea.error") })],
    ["media", t("Media siap", "Media ready"), `${count((r) => r.event === "media.done")}`,
      t("{n} gagal", "{n} failed", { n: count((r) => r.event === "media.error") })],
    ["faq", t("FAQ siap", "FAQs ready"), `${count((r) => r.event === "faq.ready")}`,
      t("{n} perlu semakan", "{n} to check", { n: count((r) => r.event === "faq.ready" && r.level === "warn") })],
    ["approved", t("Diluluskan", "Approved"), `${count((r) => r.event === "post.approved")}`,
      t("{n} kembali ke draf", "{n} back to draft", { n: count((r) => r.event === "post.unapproved" || r.event === "post.returned") })],
    ["errors", t("Ralat", "Errors"), `${count((r) => r.level === "error")}`,
      t("{n} amaran", ["{n} warning", "{n} warnings"], { n: count((r) => r.level === "warn") })],
  ];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Log</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Apa berlaku, bila, dan oleh siapa.", "What happened, when, and who did it.")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Pangkalan data menulis setiap baris pada saat sesuatu berubah: scrape, idea, draf, media, FAQ, kelulusan, penerbit "
            + "dan tetapan. Satu bentuk untuk semua, waktu Malaysia, dan setiap baris boleh dibuka ke item asalnya. Disimpan 90 hari "
            + "di sini, dan disalin ke tab Log dalam Google Sheet Semasa selepas setiap larian.",
          "The database writes every row the moment something changes: scrapes, ideas, drafts, media, FAQs, approvals, the "
            + "publisher and settings. One shape for everything, in Malaysian time, and every row opens the item it is about. Kept "
            + "90 days here, and copied to the Log tab of the Semasa Google Sheet after every run.")}
        </p>
      </motion.div>

      {log.error && (
        <p className="mt-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">
          {/semasa_log/.test(log.error) ? t("Log belum disediakan: jalankan supabase/008_log.sql sekali di Supabase SQL editor.",
            "The log is not set up yet: run supabase/008_log.sql once in the Supabase SQL editor.") : log.error}
        </p>
      )}

      <section aria-label={t("Hari ini", "Today")} className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {tiles.map(([id, label, n, sub]) => (
          <Card key={id} className="p-3">
            <p className="text-[11px] uppercase tracking-wide text-muted">{label} · {t("hari ini", "today")}</p>
            <p className="mt-1 font-display text-2xl">{n}</p>
            <p className="text-[11px] text-muted">{sub}</p>
          </Card>
        ))}
      </section>

      <div className="z-30 sm:sticky sm:top-[97px] xl:top-[65px] -mx-4 mt-4 bg-bg/85 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented value={range} onChange={setRange} options={RANGES()} />
          <Select value={level} onChange={setLevel} aria-label={t("Tahap", "Level")}
            options={[["all", t("Semua tahap", "All levels")], ["warn", t("Amaran & ralat", "Warnings & errors")], ["error", t("Ralat sahaja", "Errors only")]]} />
          <Select value={actor} onChange={setActor} aria-label={t("Oleh", "By")}
            options={[["all", t("Semua", "Everyone")], ["me", t("Tindakan anda", "Your actions")], ["bot", t("Tindakan bot", "Bot actions")]]} />
          <label className="relative min-w-0 flex-1 basis-48">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
            <Input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("Cari dalam log…", "Search the log…")} className="pl-9"
              aria-label={t("Cari log", "Search the log")} />
          </label>
          <Button size="sm" variant="ghost" disabled={!shown.length}
            onClick={() => download(new Blob([toCsv(shown)], { type: "text/csv;charset=utf-8" }), `semasa-log-${today}.csv`)}>
            <Download size={12} /> CSV</Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5 text-xs" role="tablist" aria-label={t("Bahagian", "Area")}>
          <button type="button" role="tab" aria-selected={area === "all"} onClick={() => setArea("all")}
            className={`rounded-pill px-3 py-1.5 ${area === "all" ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
            {t("Semua", "All")} · {Object.values(byArea).reduce((a, b) => a + b, 0)}</button>
          {Object.entries(AREAS).map(([k, a]) => (
            <button type="button" role="tab" key={k} aria-selected={area === k} onClick={() => setArea(k)}
              className={`inline-flex items-center gap-1 rounded-pill px-3 py-1.5 ${area === k ? "bg-ink text-bg" : "bg-surface-2 text-muted"} ${byArea[k] ? "" : "opacity-60"}`}>
              <a.icon size={11} /> {areaLabel(a)} · {byArea[k] || 0}</button>
          ))}
        </div>
      </div>

      {!days.length && !log.loading && (
        <p className="mt-4 rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Tiada peristiwa untuk tapisan ini.", "No events for this filter.")}</p>
      )}
      <div className="mt-2 space-y-5">
        {days.map(({ day, rows }) => (
          <section key={day} aria-label={dayTitle(day)}>
            <h2 className="mb-2 flex items-baseline gap-2 text-sm">
              <span className="font-display text-base">{day === today ? t("Hari ini", "Today") : dayTitle(day)}</span>
              <span className="text-[11px] text-muted">{t("{n} peristiwa", ["{n} event", "{n} events"], { n: rows.length })}</span>
            </h2>
            <ol className="divide-y divide-line overflow-hidden rounded-card border border-line bg-surface">
              {rows.map((r) => {
                const A = AREAS[r.area] || AREAS.system;
                const L = LEVEL[r.level] || LEVEL.info;
                const target = targetOf(r);
                const details = Object.entries(r.detail || {}).map(([k, v]) => [k, show(k, v)]).filter(([, v]) => v !== null);
                const isOpen = open === r.id;
                return (
                  <li key={r.id} className="px-3 py-2">
                    <div className="flex items-start gap-2 text-sm">
                      <time className="w-11 shrink-0 pt-0.5 font-mono text-[11px] text-muted" dateTime={r.at}>{clock(r.at)}</time>
                      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${L.dot}`} title={r.level} aria-label={r.level} />
                      <span className="inline-flex shrink-0 items-center gap-1 rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] text-muted"><A.icon size={10} /> {areaLabel(A)}</span>
                      <button type="button" onClick={() => setOpen(isOpen ? null : r.id)} aria-expanded={isOpen}
                        className={`min-w-0 flex-1 text-left ${r.level === "error" ? "text-danger" : "text-ink"}`}>
                        {titleOf(r.title, lang)}
                        {details.length > 0 && <ChevronDown size={12} className={`ml-1 inline transition ${isOpen ? "rotate-180" : ""}`} />}
                      </button>
                      <span className={`shrink-0 rounded-pill px-2 py-0.5 text-[10px] ${r.actor ? "bg-accent/10 text-accent" : "bg-surface-2 text-muted"}`}>{r.actor ? t("Anda", "You") : "Bot"}</span>
                      {target && onOpen && (
                        <button type="button" onClick={() => onOpen(target)} className="shrink-0 text-[11px] text-accent hover:underline" aria-label={t("Buka {x}", "Open {x}", { x: titleOf(r.title, lang) })}>
                          <ExternalLink size={12} /></button>
                      )}
                    </div>
                    {isOpen && (
                      <div className="ml-[3.25rem] mt-2 rounded-tile bg-surface-2/60 p-2 text-[12px]">
                        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
                          {details.map(([k, v]) => (
                            <div key={k} className="contents">
                              <dt className="text-muted">{labelOf(k)}</dt>
                              <dd className="[overflow-wrap:anywhere]">{v}</dd>
                            </div>
                          ))}
                        </dl>
                        <p className="mt-2 font-mono text-[10px] text-muted">{r.event} · {new Date(r.at).toISOString()}</p>
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>
    </main>
  );
}

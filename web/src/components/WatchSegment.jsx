import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Eye, EyeOff, ExternalLink, Lightbulb, Link2, Loader2, RefreshCw, Search, Trash2 } from "lucide-react";
import { fadeUp, stagger } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { currentLang, useLang } from "../lib/i18n";
import { stampMYT } from "../lib/format";
import Button from "./ui/Button";
import Card from "./ui/Card";
import Skeleton from "./ui/Skeleton";
import { Input, Select } from "./ui/Field";
import ViewToggle, { TBODY, TD, TH, THEAD, TR, TableFrame, useView } from "./ViewToggle";

/* Regulatory and Latest publication: the regulators' own notices and PubMed's newest papers, swept once a day by the
   worker (backend/semasa/watch.py → semasa_watch). Same flow as a headline: read it here, "Jadikan idea", and the idea
   becomes a post, a carousel or a poster. The page may only hide a row; everything else is the worker's. */

/** A notice's own date (a calendar date, not a moment): shown as written, never shifted by a time zone. */
export function dayText(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(currentLang() === "en" ? "en-GB" : "ms-MY",
    { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" }).format(d);
}

/** The paper's citation in one line: authors, journal, year, DOI (what the writer must cite, and Wan checks). */
export function paperLine(r) {
  const raw = r.raw || {};
  const au = Array.isArray(raw.authors) ? raw.authors : [];
  const who = au.length ? au.slice(0, 3).join(", ") + (au.length > 3 ? " et al." : "") : "";
  const year = r.published_at ? String(r.published_at).slice(0, 4) : "";
  return [who, raw.journal, year, raw.doi ? `DOI ${raw.doi}` : "", raw.pmid ? `PMID ${raw.pmid}` : ""].filter(Boolean).join(" · ");
}

/** A watch row as the idea composer's "trend": the summary carries everything the writer needs to cite it. */
export function watchIdea(r, brand) {
  const raw = r.raw || {};
  const pub = r.section === "publication";
  const domains = (brand && brand.regulab && brand.regulab.domains) || {};
  const summary = [
    r.summary,
    r.why ? `Kenapa penting: ${r.why}` : "",
    r.kind ? `Jenis: ${r.kind}${raw.ref ? ` (${raw.ref})` : ""}` : "",
    pub ? `Kertas: ${paperLine(r)}` : "",
    pub && raw.abstract ? `Abstrak: ${raw.abstract}` : "",
  ].filter(Boolean).join("\n\n");
  return {
    watch: true, section: r.section, id: r.id, title: r.title, url: r.url, source: r.source, summary,
    domain: domains[r.domain] ? r.domain : "",
    // a paper speaks to peers (LinkedIn, angle F: cosmetic science; G: medicine or dermatology); a notice to SMEs
    stream: pub ? "linkedin" : "regulab",
    angle: pub ? (r.domain === "farmaseutikal" ? "G" : "F") : "",
  };
}

function Pill({ active, onClick, children }) {
  return (
    <button type="button" onClick={onClick}
      className={`rounded-pill px-3 py-1 text-[11px] font-semibold uppercase tracking-wide ${active ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>
      {children}
    </button>
  );
}

const isReading = (r) => r.status === "pending" || r.status === "working";

function Actions({ row, onIdea, onHide, onRemove, busy }) {
  const { t } = useLang();
  if (isReading(row) || row.status === "error") {
    return (
      <span className="flex flex-wrap items-center gap-3">
        {isReading(row) && <span className="inline-flex items-center gap-1.5 text-xs text-muted"><Loader2 size={13} className="animate-spin" />
          {t("Sedang dibaca…", "Being read…")}</span>}
        <button type="button" disabled={busy} onClick={() => onRemove(row)}
          className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-danger disabled:opacity-50">
          <Trash2 size={13} /> {t("Buang", "Remove")}</button>
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-3">
      {onIdea && (
        <button type="button" onClick={() => onIdea(row)} className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-accent hover:underline">
          <Lightbulb size={13} /> {t("Jadikan idea", "Make an idea")}
        </button>
      )}
      <button type="button" disabled={busy} onClick={() => onHide(row)}
        className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-ink disabled:opacity-50">
        {row.dismissed ? <><Eye size={13} /> {t("Tunjuk semula", "Show again")}</> : <><EyeOff size={13} /> {t("Sembunyi", "Hide")}</>}
      </button>
      {row.pasted && (
        <button type="button" disabled={busy} onClick={() => onRemove(row)}
          className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-danger disabled:opacity-50">
          <Trash2 size={13} /> {t("Buang", "Remove")}</button>
      )}
    </span>
  );
}

function Tags({ row, domainLabel }) {
  const { t } = useLang();
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-1.5">
      <span className="max-w-full truncate rounded-pill bg-accent/10 px-2 py-0.5 text-[11px] font-semibold text-accent">{row.source || t("Pautan", "Link")}</span>
      {row.pasted && <span className="rounded-pill bg-ink/5 px-2 py-0.5 text-[11px] text-ink">{t("ditampal", "pasted")}</span>}
      {row.kind && row.section === "regulatory" && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted">{row.kind}</span>}
      {row.domain && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[11px] text-muted">{domainLabel(row.domain)}</span>}
      {row.relevant === false && !row.pasted && <span className="rounded-pill bg-warn/10 px-2 py-0.5 text-[11px] text-warn">{t("kurang berkaitan", "less relevant")}</span>}
    </span>
  );
}

function WatchCard({ row, onIdea, onHide, onRemove, busy, domainLabel }) {
  const { t } = useLang();
  const pub = row.section === "publication";
  return (
    <motion.div variants={fadeUp} layout>
      <Card as="article" className={`overflow-hidden ${row.dismissed ? "opacity-60" : ""}`}>
        <div className="flex items-start justify-between gap-2 px-4 pt-4">
          <Tags row={row} domainLabel={domainLabel} />
          <time className="shrink-0 text-[11px] text-muted" title={row.created_at ? t("Dikutip {at}", "Collected {at}", { at: stampMYT(row.created_at) }) : ""}>
            {dayText(row.published_at || row.created_at)}
          </time>
        </div>
        <a href={row.url} target="_blank" rel="noopener noreferrer" className="group block px-4 pb-4 pt-3">
          <h3 className="[overflow-wrap:anywhere] font-display text-[17px] leading-snug text-ink group-hover:text-accent">
            {row.title} <ExternalLink size={12} className="inline align-baseline text-muted" />
          </h3>
          {row.status === "error" && row.error && (
            <p className="mt-2 flex gap-1.5 rounded-tile bg-danger/5 p-2 text-[12px] text-danger [overflow-wrap:anywhere]">
              <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {row.error}</p>
          )}
          {pub && paperLine(row) && <p className="mt-1.5 text-[12px] text-muted [overflow-wrap:anywhere]">{paperLine(row)}</p>}
          {row.summary && <p className="mt-2 text-sm leading-relaxed text-muted [overflow-wrap:anywhere]">{row.summary}</p>}
          {row.why && (
            <p className="mt-3 rounded-tile bg-surface-2 p-2.5 text-[13px] leading-relaxed text-ink [overflow-wrap:anywhere]">
              <span className="block text-[10px] font-semibold uppercase tracking-wide text-muted">{t("Kenapa penting", "Why it matters")}</span>
              {row.why}
            </p>
          )}
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-muted">
            {row.country && <span>{row.country}</span>}
            {row.summary_source === "llm" && <span className="rounded-pill bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">AI</span>}
            <span className="uppercase">{row.lang}</span>
          </p>
        </a>
        <div className="border-t border-line/70 px-4 py-2"><Actions row={row} onIdea={onIdea} onHide={onHide} onRemove={onRemove} busy={busy} /></div>
      </Card>
    </motion.div>
  );
}

function WatchTable({ rows, onIdea, onHide, onRemove, busyId, domainLabel }) {
  const { t } = useLang();
  return (
    <TableFrame label={t("Senarai", "List")}>
      <thead className={THEAD}>
        <tr>
          <th className={TH}>{t("Sumber", "Source")}</th>
          <th className={`${TH} w-[50%]`}>{t("Tajuk", "Title")}</th>
          <th className={TH}>{t("Tarikh", "Date")}</th>
          <th className={TH}>{t("Tindakan", "Actions")}</th>
        </tr>
      </thead>
      <tbody className={TBODY}>
        {rows.map((r) => (
          <tr key={r.id} className={`${TR} hover:bg-surface-2/50 ${r.dismissed ? "opacity-60" : ""}`}>
            <td className={TD} data-label={t("Sumber", "Source")}><Tags row={r} domainLabel={domainLabel} /></td>
            <td className={`${TD} [overflow-wrap:anywhere]`} data-label={t("Tajuk", "Title")}>
              <a href={r.url} target="_blank" rel="noopener noreferrer" className="font-medium leading-snug hover:text-accent">
                {r.title} <ExternalLink size={11} className="inline align-baseline text-muted" /></a>
              {r.status === "error" && r.error && <p className="mt-1 text-[12px] text-danger">{r.error}</p>}
              {r.section === "publication" && paperLine(r) && <p className="mt-0.5 text-[11px] text-muted">{paperLine(r)}</p>}
              {r.summary && <p className="mt-1 line-clamp-3 text-[12px] text-muted">{r.summary}</p>}
              {r.why && <p className="mt-1 text-[12px] text-ink"><span className="font-semibold">{t("Kenapa penting:", "Why it matters:")}</span> {r.why}</p>}
            </td>
            <td className={`${TD} whitespace-nowrap text-[12px] text-muted`} data-label={t("Tarikh", "Date")}>{dayText(r.published_at || r.created_at)}</td>
            <td className={TD} data-label={t("Tindakan", "Actions")}><Actions row={r} onIdea={onIdea} onHide={onHide} onRemove={onRemove} busy={busyId === r.id} /></td>
          </tr>
        ))}
      </tbody>
    </TableFrame>
  );
}

/** One segment (regulatory | publication) over the shared semasa_watch rows. */
/* Paste a link (Wan, 26 Sep 2026: "allow us to paste the link as well"): the page adds the row, the worker reads it
   (backend/semasa/watch.py process_pasted) and it becomes an item like any swept one. */
function PasteLink({ section, user, onToast, onAdded }) {
  const { t } = useLang();
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const pub = section === "publication";
  async function add(e) {
    e.preventDefault();
    const link = url.trim();
    if (!/^https?:\/\/\S+\.\S+/.test(link)) return onToast(t("Tampal pautan penuh, bermula dengan https://", "Paste a full link, starting with https://"), "warn");
    let host = "";
    try { host = new URL(link).hostname.replace(/^www\./, ""); } catch { /* the test above already passed */ }
    setBusy(true);
    const { error } = await supabase.from(TABLES.watch).insert({
      section, url: link, title: title.trim() || link, source: host, status: "pending", pasted: true, created_by: user.id,
    });
    setBusy(false);
    if (error) {
      if (error.code === "23505") return onToast(t("Pautan ini sudah ada dalam senarai (mungkin disembunyikan).", "This link is already in the list (it may be hidden)."), "warn");
      return onToast(/pasted|status|column/.test(errText(error))
        ? t("Belum disediakan: jalankan supabase/013_watch_paste.sql sekali.", "Not set up yet: run supabase/013_watch_paste.sql once.")
        : errText(error), "danger");
    }
    setUrl(""); setTitle("");
    onToast(t("Ditampal. Pekerja membacanya dalam beberapa minit.", "Pasted. The worker reads it within a few minutes."), "ok");
    onAdded?.();
  }
  return (
    <form onSubmit={add} className="mt-4 rounded-card border border-line bg-surface p-3 shadow-card sm:p-4">
      <p className="mb-2 flex items-center gap-1.5 text-sm font-medium"><Link2 size={15} className="text-accent" />
        {pub ? t("Tampal pautan kertas", "Paste a paper's link") : t("Tampal pautan notis", "Paste a notice's link")}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input type="url" value={url} onChange={(e) => setUrl(e.target.value)} required aria-label={t("Pautan", "Link")} className="sm:flex-[2]"
          placeholder={pub ? "https://pubmed.ncbi.nlm.nih.gov/… · https://doi.org/10.…" : "https://www.npra.gov.my/… (halaman atau PDF)"} />
        <Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={300} aria-label={t("Nama (pilihan)", "Name (optional)")} className="sm:flex-1"
          placeholder={t("Nama (pilihan)", "Name (optional)")} />
        <Button type="submit" size="sm" disabled={busy || !url.trim()} className="justify-center">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Link2 size={12} />} {t("Tampal", "Paste")}</Button>
      </div>
      <p className="mt-2 text-[11px] text-muted">{pub
        ? t("PubMed atau DOI paling tepat: pengarang, jurnal, tahun dan abstrak diambil terus dari PubMed. Laman jurnal juga boleh.",
          "PubMed or a DOI works best: authors, journal, year and abstract come straight from PubMed. A journal page works too.")
        : t("Laman atau PDF pengawal selia (NPRA, JAKIM, KKM, HSA, EU, UK…): bot baca teks dan menamakan pengawal selia sebagai sumber.",
          "A regulator's page or PDF (NPRA, JAKIM, KKM, HSA, EU, UK…): the bot reads its text and names the regulator as the source.")}</p>
    </form>
  );
}

export default function WatchSegment({ section, watch, setting, saveSetting, brand, user, onIdea, onToast }) {
  const { t } = useLang();
  const [view, setView] = useView(`watch.${section}`);
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("");
  const [source, setSource] = useState("");
  const [showLess, setShowLess] = useState(false);
  const [showHidden, setShowHidden] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [asking, setAsking] = useState(false);

  const domains = (brand && brand.regulab && brand.regulab.domains) || {};
  const domainLabel = (d) => (d === "lain" ? t("Lain-lain", "Other") : domains[d] || d);

  const mine = useMemo(() => watch.rows.filter((r) => r.section === section)
    .sort((a, b) => String(b.published_at || b.created_at || "").localeCompare(String(a.published_at || a.created_at || ""))),
  [watch.rows, section]);
  const visible = useMemo(() => mine.filter((r) => (showHidden || !r.dismissed) && (showLess || r.pasted || r.relevant !== false)),
    [mine, showHidden, showLess]);
  const counts = useMemo(() => {
    const c = {};
    for (const r of visible) if (r.domain) c[r.domain] = (c[r.domain] || 0) + 1;
    return c;
  }, [visible]);
  const sources = useMemo(() => [...new Set(visible.map((r) => (section === "publication" ? r.source.replace(/^PubMed · /, "") : r.source)))].sort(),
    [visible, section]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return visible.filter((r) => (!domain || r.domain === domain)
      && (!source || r.source === source || r.source === `PubMed · ${source}`)
      && (!q || [r.title, r.summary, r.why, r.source, r.kind, r.raw && r.raw.doi].some((v) => String(v || "").toLowerCase().includes(q))));
  }, [visible, domain, source, query]);
  const hiddenN = mine.filter((r) => r.dismissed).length;
  // while a pasted link is being read, look again every 15 seconds rather than every two minutes
  const reading = mine.some(isReading);
  const reload = watch.reload;
  useEffect(() => {
    if (!reading) return undefined;
    const id = setInterval(() => { if (!document.hidden) reload(); }, 15_000);
    return () => clearInterval(id);
  }, [reading, reload]);

  async function remove(r) {
    setBusyId(r.id);
    const { data, error } = await supabase.from(TABLES.watch).delete().eq("id", r.id).select("id");
    setBusyId(null);
    if (error) return onToast(errText(error), "danger");
    if (!data?.length) return onToast(t("Tidak dibuang: hanya pautan yang ditampal boleh dibuang.", "Not removed: only a pasted link can be removed."), "warn");
    onToast(t("Dibuang.", "Removed."), "info");
    watch.reload();
  }
  const lessN = mine.filter((r) => r.relevant === false && !r.pasted && !r.dismissed).length;

  async function hide(r) {
    setBusyId(r.id);
    const { data, error } = await supabase.from(TABLES.watch).update({ dismissed: !r.dismissed }).eq("id", r.id).select("id");
    setBusyId(null);
    if (error) return onToast(errText(error), "danger");
    if (!data?.length) return onToast(t("Tidak disimpan: hanya pemuat naik boleh menyembunyikan.", "Not saved: only uploaders can hide an item."), "warn");
    onToast(r.dismissed ? t("Ditunjuk semula.", "Shown again.") : t("Disembunyikan.", "Hidden."), "info");
    watch.reload();
  }

  const s = setting || {};
  const res = s.result || {};
  const failing = (res.sources || []).filter((x) => !x.ok);
  const waiting = Boolean(s.force);

  async function sweepNow() {
    setAsking(true);
    try {
      await saveSetting("watch", { ...s, force: true });
      onToast(t("Diminta. Pekerja akan menyapu dalam beberapa minit; senarai dikemas kini sendiri.",
        "Asked. The worker sweeps within a few minutes; the list updates by itself."), "ok");
    } catch (e) {
      onToast(/not found/.test(e.message)
        ? t("Belum disediakan: jalankan supabase/012_watch.sql sekali.", "Not set up yet: run supabase/012_watch.sql once.") : e.message, "danger");
    } finally { setAsking(false); }
  }

  const missing = /semasa_watch/.test(watch.error || "");
  return (
    <>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
        {s.last_run
          ? <span>{t("Sapuan terakhir {at} · {n} baharu", "Last sweep {at} · {n} new", { at: stampMYT(s.last_run), n: res.new ?? 0 })}</span>
          : <span>{t("Belum pernah disapu.", "Not swept yet.")}</span>}
        {res.error && <span className="rounded-pill bg-danger/10 px-2 py-0.5 text-danger" title={res.error}>{t("sapuan gagal", "sweep failed")}</span>}
        {failing.length > 0 && (
          <span className="rounded-pill bg-danger/10 px-2 py-0.5 text-danger" title={failing.map((x) => `${x.name}: ${x.error}`).join("\n")}>
            {t("{n} sumber gagal", ["{n} source failed", "{n} sources failed"], { n: failing.length })}
          </span>
        )}
        <Button variant="ghost" size="sm" onClick={sweepNow} disabled={asking || waiting}>
          <RefreshCw size={12} className={waiting ? "animate-spin" : ""} />
          {waiting ? t("Menunggu pekerja…", "Waiting for the worker…") : t("Sapu sekarang", "Sweep now")}
        </Button>
      </div>

      {user && <PasteLink section={section} user={user} onToast={onToast} onAdded={() => watch.reload()} />}

      <div className="z-30 sm:sticky sm:top-[97px] xl:top-[65px] -mx-4 mt-4 bg-bg/85 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex min-w-0 flex-1 basis-60 items-center gap-2 rounded-pill border border-line bg-surface px-4 py-2 shadow-card">
              <Search size={15} className="shrink-0 text-muted" />
              <input value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder={section === "publication" ? t("Cari tajuk, jurnal, DOI…", "Search titles, journals, DOIs…") : t("Cari tajuk, sumber, ringkasan…", "Search titles, sources, summaries…")}
                className="w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-muted" />
            </label>
            {sources.length > 1 && (
              <Select value={source} onChange={setSource} className="max-w-full"
                options={[["", section === "publication" ? t("Semua jurnal", "All journals") : t("Semua sumber", "All sources")], ...sources.map((x) => [x, x])]} />
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            <Pill active={!domain} onClick={() => setDomain("")}>{t("Semua", "All")} · {visible.length}</Pill>
            {Object.entries(counts).map(([d, n]) => (
              <Pill key={d} active={domain === d} onClick={() => setDomain(domain === d ? "" : d)}>{domainLabel(d)} · {n}</Pill>
            ))}
          </div>
        </div>
      </div>

      {watch.error && (
        <p className="my-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">
          {missing ? t("Segmen ini belum disediakan: jalankan supabase/012_watch.sql sekali.", "This segment is not set up yet: run supabase/012_watch.sql once.") : watch.error}
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <span className="flex flex-wrap gap-4 text-xs text-muted">
          <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={showLess} onChange={(e) => setShowLess(e.target.checked)} />
            {t("Tunjuk yang kurang berkaitan ({n})", "Show less relevant ({n})", { n: lessN })}</label>
          <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />
            {t("Tunjuk yang disembunyikan ({n})", "Show hidden ({n})", { n: hiddenN })}</label>
        </span>
        <ViewToggle view={view} setView={setView} />
      </div>
      <div className="mt-3">
        {watch.loading ? (
          <div className="masonry">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} style={{ height: 160 + (i % 3) * 40 }} />)}</div>
        ) : !rows.length ? (
          <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">
            {mine.length ? t("Tiada yang sepadan.", "Nothing matches.") : t("Belum ada item. Sapuan berjalan sekali sehari; tekan Sapu sekarang untuk mula.",
              "No items yet. The sweep runs once a day; press Sweep now to start.")}
          </p>
        ) : view === "table" ? (
          <WatchTable rows={rows} onIdea={onIdea} onHide={hide} onRemove={remove} busyId={busyId} domainLabel={domainLabel} />
        ) : (
          <motion.div className="masonry" variants={stagger(0.03)} initial="hidden" animate="show">
            {rows.map((r) => <WatchCard key={r.id} row={r} onIdea={onIdea} onHide={hide} onRemove={remove} busy={busyId === r.id} domainLabel={domainLabel} />)}
          </motion.div>
        )}
      </div>
    </>
  );
}

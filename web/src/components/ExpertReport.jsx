import { useMemo } from "react";
import { ArrowDownUp, ExternalLink, FileDown, FileSpreadsheet, FileText, Printer } from "lucide-react";
import { useLang } from "../lib/i18n";
import { CSV_MIME, DOC_MIME, docFile, fileName, groupByDay, dayHeading, printHtml, printReport, reportCsv, reportItems, reportMeta } from "../lib/expertReport";
import { download } from "../lib/faqExport";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { TBODY, TD, TH, THEAD, TR, TableFrame } from "./ViewToggle";

/* Expert content as a report table (Wan, 23 Nov 2026): the posts the page is showing now (the open category, the search and the
   account filter already applied), one row each, in timeline order, with the full original post, and four ways out: Print, PDF
   (the browser's own "Save as PDF" from the print dialog: the repo has no PDF writer, and a hand-made one could not carry Malay
   and Chinese text), CSV for Excel, and a Word .doc. The files are made here from the rows already loaded; nothing is fetched. */

export default function ExpertReport({ rows, category, account, q, hidden, order, setOrder, onToast }) {
  const { t, lang } = useLang();
  const l = lang === "en" ? "en" : "bm";
  const items = useMemo(() => reportItems(rows, { order, lang: l }), [rows, order, l]);
  const groups = useMemo(() => groupByDay(items), [items]);
  const stamp = () => reportMeta(items, { category, order, account, q, hidden, now: new Date(), lang: l });
  const empty = !items.length;

  const run = (kind) => {
    if (empty) return;
    const meta = stamp();
    try {
      if (kind === "print" || kind === "pdf") {
        printReport(printHtml(items, meta));
        if (kind === "pdf") onToast(t("Pilih “Simpan sebagai PDF” sebagai pencetak dalam tetingkap yang terbuka.", "In the window that opens, choose “Save as PDF” as the printer."), "ok");
      } else if (kind === "csv") {
        download(new Blob([reportCsv(items, { lang: l })], { type: CSV_MIME }), fileName(meta, items, "csv"));
      } else if (kind === "doc") {
        download(new Blob([docFile(items, meta)], { type: `${DOC_MIME};charset=utf-8` }), fileName(meta, items, "doc"));
      }
    } catch (e) { onToast(e.message, "danger"); }
  };

  const btn = (kind, Icon, label, hint) => (
    <Button type="button" size="sm" variant="ghost" disabled={empty} onClick={() => run(kind)} title={hint} data-report-export={kind}><Icon size={14} /> {label}</Button>
  );

  return (
    <div data-expert-report>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setOrder(order === "oldest" ? "newest" : "oldest")} data-report-order={order}
          title={t("Tukar susunan garis masa", "Change the timeline order")}
          className="inline-flex min-h-[44px] items-center gap-1.5 rounded-pill border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface-2 lg:min-h-0">
          <ArrowDownUp size={13} /> {order === "oldest" ? t("Terlama dahulu", "Oldest first") : t("Terbaharu dahulu", "Newest first")}</button>
        <span className="mx-1 hidden h-5 w-px bg-line sm:inline-block" aria-hidden="true" />
        {btn("print", Printer, t("Cetak", "Print"), t("Cetak laporan (A4 melintang)", "Print the report (A4 landscape)"))}
        {btn("pdf", FileDown, "PDF", t("Buka tetingkap cetak, pilih Simpan sebagai PDF", "Opens the print window: choose Save as PDF"))}
        {btn("csv", FileSpreadsheet, "CSV", t("Fail CSV untuk Excel (UTF-8)", "A CSV file for Excel (UTF-8)"))}
        {btn("doc", FileText, "DOC", t("Fail Word (.doc) dengan jadual", "A Word (.doc) file with the table"))}
      </div>
      <p className="mb-3 text-xs text-muted" data-report-note>
        {t("{n} catatan dalam laporan ini, mengikut garis masa (masa Malaysia). Eksport memuatkan apa yang dipaparkan: kategori, carian dan akaun yang dipilih.",
          "{n} post(s) in this report, in timeline order (Malaysia time). The exports hold what is shown: the category, search and account chosen.", { n: items.length })}
      </p>

      {empty ? (
        <Card className="p-6 text-center text-sm text-muted" data-report-empty>{t("Tiada catatan untuk dilaporkan.", "No posts to report.")}</Card>
      ) : (
        <TableFrame label={t("Laporan kandungan pakar", "Expert content report")}>
          <thead className={THEAD}>
            <tr>
              {[t("Bil.", "No."), t("Tarikh dan masa", "Date and time"), t("Pakar", "Expert"), t("Kategori", "Category"), t("Ringkasan", "Summary"),
                t("Apa yang boleh diambil", "What to take from it"), t("Catatan asal", "Original post"), t("Pautan", "Link")].map((h) => <th key={h} className={`${TH} text-left`}>{h}</th>)}
            </tr>
          </thead>
          {groups.map((g) => (
            <tbody key={g.date || "unknown"} className={TBODY} data-report-day={g.date || "unknown"}>
              <tr className="block bg-surface-2 md:table-row">
                <td colSpan={8} className="block px-3 py-1.5 text-xs font-semibold text-ink md:table-cell">
                  {g.date ? dayHeading(g.date, l) : t("Masa tidak diketahui", "Time unknown")} <span className="font-normal text-muted">· {g.items.length}</span></td>
              </tr>
              {g.items.map((x) => (
                <tr key={x.id || x.n} className={TR} data-report-row={x.id}>
                  <td className={`${TD} tabular-nums text-muted`} data-label={t("Bil.", "No.")}>{x.n}</td>
                  <td className={`${TD} whitespace-nowrap`} data-label={t("Tarikh dan masa", "Date and time")}>
                    <span className="font-semibold text-ink">{x.date || "-"}</span>{x.time && <span className="block text-xs text-muted tabular-nums">{x.time} MYT</span>}
                    {x.timeIsCollected && <span className="block text-[10px] text-muted">{t("masa dikutip", "time collected")}</span>}</td>
                  <td className={TD} data-label={t("Pakar", "Expert")}>
                    <span className="font-semibold text-ink">{x.expert}</span>
                    <span className="block text-xs text-muted">{x.handle && `@${x.handle} · `}{x.platform}</span></td>
                  <td className={TD} data-label={t("Kategori", "Category")}>{x.category}</td>
                  <td className={`${TD} md:min-w-[16rem]`} data-label={t("Ringkasan", "Summary")}>
                    <span className="block font-semibold text-ink [overflow-wrap:anywhere]">{x.title}</span>
                    <span className="block text-ink/90 [overflow-wrap:anywhere]">{x.summary}</span></td>
                  <td className={`${TD} [overflow-wrap:anywhere] md:min-w-[12rem]`} data-label={t("Apa yang boleh diambil", "What to take from it")}>{x.why}</td>
                  <td className={`${TD} whitespace-pre-line [overflow-wrap:anywhere] md:min-w-[18rem]`} data-label={t("Catatan asal", "Original post")}>{x.original}</td>
                  <td className={TD} data-label={t("Pautan", "Link")}>
                    {x.link && <a href={x.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline"><ExternalLink size={12} /> {t("Buka", "Open")}</a>}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </TableFrame>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Download, Printer } from "lucide-react";
import { useLang } from "../lib/i18n";
import { supabase } from "../lib/SupabaseClient";
import { documentHtml } from "../lib/billingDoc";
import { effectiveStatus, kindLabel, money, publicLink, statusLabel } from "../lib/billing";
import { qrDataUrl } from "../lib/qr";

/* The client's side of Bil: #bil/<token> opens the paper (quotation, invoice or receipt) with no sign-in. The database
   function semasa_billing_public (supabase/028) hands back the document, the company's details and, for an invoice,
   the bank details; opening it the first time marks the document VIEWED. Print = the browser's own "Save as PDF"; the
   Download button is the worker's PDF when one has been made. Nothing here can change the document. */
export default function BillingPublic({ token }) {
  const { t } = useLang();
  const [data, setData] = useState(undefined);        // undefined = loading, null = not found
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    (async () => {
      const { data: d, error: e } = await supabase.rpc("semasa_billing_public", { p_token: token });
      if (!live) return;
      if (e) setError(e.message || String(e));
      setData(d || null);
    })();
    return () => { live = false; };
  }, [token]);

  const base = `${import.meta.env.BASE_URL}cards/`;
  const html = useMemo(() => {
    if (!data?.doc) return "";
    const abs = (p) => new URL(p, window.location.href).href;
    const site = `${window.location.origin}${window.location.pathname}`;
    return documentHtml(data.doc, { company: data.company || {}, bank: data.bank || {} },
      { logoUrl: abs(`${base}logo-ink.png`), fontsCss: abs(`${base}fonts.css`), qr: qrDataUrl(publicLink(token, site)) });
  }, [data, token, base]);

  function print() {
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.open(); w.document.write(html); w.document.close();
    w.addEventListener("load", () => { w.focus(); w.print(); });
    setTimeout(() => { try { w.focus(); w.print(); } catch { /* already printed */ } }, 600);
  }

  if (data === undefined && !error) return <main className="grid min-h-screen place-items-center text-sm text-muted">…</main>;
  if (error || !data?.doc) {
    return (
      <main className="grid min-h-screen place-items-center px-6 text-center">
        <div>
          <h1 className="font-display text-xl">{t("Dokumen tidak dijumpai", "Document not found")}</h1>
          <p className="mt-2 text-sm text-muted">{t("Pautan ini tidak sah atau dokumen itu telah ditarik balik.", "This link is not valid or the document has been withdrawn.")}</p>
          {error && <p className="mt-2 text-xs text-danger">{error}</p>}
        </div>
      </main>
    );
  }
  const d = data.doc;
  const st = effectiveStatus(d);
  const lang = d.lang === "en" ? "en" : "bm";
  const tone = st === "paid" ? "bg-ok/10 text-ok" : st === "overdue" || st === "expired" ? "bg-danger/10 text-danger" : "bg-surface-2 text-ink";
  return (
    <main className="min-h-screen bg-bg">
      <div className="mx-auto flex max-w-[900px] flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div>
          <div className="text-[11px] uppercase tracking-widest text-muted">{data.company?.name}</div>
          <h1 className="font-display text-lg">{kindLabel(d.kind, lang)} {d.number}</h1>
          <div className="mt-1 flex items-center gap-2 text-sm">
            <span className={`rounded-pill px-2 py-0.5 text-xs font-medium ${tone}`}>{statusLabel(st, lang)}</span>
            <span className="text-muted">{money(d.total, { currency: d.currency || "MYR" })}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={print} className="inline-flex items-center gap-2 rounded-pill bg-accent px-4 py-2 text-sm font-medium text-accent-ink">
            <Printer size={14} /> {lang === "en" ? "Print / Save as PDF" : "Cetak / Simpan PDF"}
          </button>
          {d.pdf_url && (
            <a href={d.pdf_url} download className="inline-flex items-center gap-2 rounded-pill border border-line bg-surface px-4 py-2 text-sm">
              <Download size={14} /> PDF
            </a>
          )}
        </div>
      </div>
      <iframe title={`${d.kind} ${d.number}`} srcDoc={html} className="block h-[calc(100vh-96px)] w-full border-0" />
    </main>
  );
}

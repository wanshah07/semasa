import { useMemo, useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";
import { canvaBrief } from "../lib/canvaBrief";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import { Modal } from "./ui/Field";

/* "Rebuild in Canva" (Wan, 4 Oct 2026): the second choice beside Semasa's own drawing. The brief carries the words, the
   size, the look's colours and fonts and the drawn pictures as a reference (web/src/lib/canvaBrief.js); it is pasted into a
   Claude chat that has the Canva connector, which builds the editable design. Nothing is sent from this page. */
export default function CanvaHandoff({ open, onClose, slides, urls, stream, size, look, citation, eyebrow, kind, sizeName }) {
  const { t } = useLang();
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => (open ? canvaBrief({ slides, urls, stream, size, look, citation, eyebrow, kind, sizeName }) : ""),
    [open, slides, urls, stream, size, look, citation, eyebrow, kind, sizeName]);
  async function copy() {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2500); }
    catch { document.getElementById("canva-brief")?.select(); }
  }
  return (
    <Modal open={open} onClose={onClose} title={t("Bina semula dalam Canva", "Rebuild in Canva")}>
      <div className="space-y-3">
        <p className="text-[12px] text-muted">
          {t("Semasa melukis kad ini sendiri, percuma. Untuk pilihan kedua, salin arahan di bawah ke chat Claude yang ada penyambung Canva: ia membina reka bentuk Canva yang boleh disunting, perkataan yang sama, saiz yang sama, warna dan fon keluarga reka bentuk ini.",
            "Semasa draws this card itself, free. For the second choice, copy the brief below into a Claude chat that has the Canva connector: it builds an editable Canva design with the same words, the same size and this look's colours and fonts.")}
        </p>
        <textarea id="canva-brief" readOnly value={text} rows={14} onFocus={(e) => e.target.select()}
          className="w-full resize-y rounded-tile border border-line bg-surface-2 p-2 font-mono text-[11px] leading-relaxed" aria-label={t("Arahan untuk Canva", "Brief for Canva")} />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <a href="https://www.canva.com/" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline">
            <ExternalLink size={12} /> {t("Buka Canva", "Open Canva")}</a>
          <Button type="button" size="sm" onClick={copy}>{copied ? <Check size={12} /> : <Copy size={12} />} {copied ? t("Disalin", "Copied") : t("Salin arahan", "Copy the brief")}</Button>
        </div>
        <p className="text-[11px] text-muted">
          {t("Penyambung Canva perlu dibenarkan dalam tetapan claude.ai. Semasa tidak menghantar apa-apa ke Canva dari halaman ini.",
            "The Canva connector has to be authorised in your claude.ai settings. Semasa sends nothing to Canva from this page.")}</p>
      </div>
    </Modal>
  );
}

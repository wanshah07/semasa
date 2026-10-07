/* The QR code on a document, made in the page (qrcode-generator, pure JS). The worker makes its own with segno
   (backend/semasa/billing.py qr_data_url); both encode the document's public "view online" link. */
import qrcode from "qrcode-generator";

/** A GIF data URL of the QR for `text`, or "" when the text is empty. */
export function qrDataUrl(text, { cell = 6, margin = 1 } = {}) {
  if (!text) return "";
  try {
    const qr = qrcode(0, "M");            // type 0 = the smallest version that fits
    qr.addData(String(text));
    qr.make();
    return qr.createDataURL(cell, margin);
  } catch {
    return "";
  }
}

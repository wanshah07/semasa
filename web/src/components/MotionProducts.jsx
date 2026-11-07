import { useMemo, useState } from "react";
import { ImagePlus, Loader2, Trash2, Upload } from "lucide-react";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { businessList } from "../lib/businesses";
import { uploadMotionAsset } from "../lib/motionAssetStorage";
import { MAX_PRODUCTS, libraryPictures } from "../lib/motionTemplates";
import Button from "./ui/Button";
import { Input, Label, Modal, Select } from "./ui/Field";

/* The products of a showcase film (Wan, 7 Nov 2026): the business whose logo and tagline go on top, and 1 to 5 products, each
   with its OWN picture, picked from the image library (uploads to the library included) or uploaded here to the private motion
   bucket. Only the background is AI; a product picture never is. The library picture is saved by id, so the worker reads its
   address from the database rather than from the browser. */
export default function MotionProducts({ products, onProducts, businessId, onBusiness, tagline, onTagline, client, user, onBusy }) {
  const { t } = useLang();
  const [picking, setPicking] = useState(false);
  const [owned, setOwned] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const mediaT = useTable(TABLES.media, { enabled: picking, select: "id,status,type,mode,generated_media_url,prompt,meta,created_at", limit: 120, realtime: false, everyMs: 300_000 });
  const bizT = useTable(TABLES.businesses, { enabled: true, order: "sort", ascending: true, limit: 50, realtime: false });
  const businesses = useMemo(() => businessList(bizT.rows), [bizT.rows]);
  const library = useMemo(() => libraryPictures(mediaT.rows), [mediaT.rows]);
  const full = products.length >= MAX_PRODUCTS;
  const set = (i, patch) => onProducts(products.map((p, k) => (k === i ? { ...p, ...patch } : p)));
  const pick = (pic) => { if (!full) onProducts([...products, { media_id: pic.id, thumb: pic.url, name: "", benefits: "" }]); setPicking(false); };
  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || full) return;
    if (!file.type.startsWith("image/")) { setError(t("Pilih fail gambar (PNG, JPEG atau WebP).", "Choose a picture file (PNG, JPEG or WebP).")); return; }
    setUploading(true); onBusy?.(true); setError("");
    try {
      const ref = await uploadMotionAsset(client, user, file, { rights: "self-owned", role: "product", source: "", attribution: "" });
      onProducts([...products, { ref, thumb: URL.createObjectURL(file), name: "", benefits: "" }]);
    } catch (err) { setError(err.message || String(err)); } finally { setUploading(false); onBusy?.(false); }
  };

  return (
    <div className="space-y-3 rounded-tile border border-line p-3" data-motion-products>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block"><Label hint={t("logo dan namanya di atas filem", "its logo and name sit on top of the film")}>{t("Syarikat", "Business")}</Label>
          <Select className="w-full" value={businessId} onChange={onBusiness} options={businesses.map((b) => [b.id, b.name])} /></label>
        <label className="block"><Label hint={t("pilihan; kosong = tagline syarikat jika ada", "optional; empty = the business's own, if it has one")}>{t("Tagline", "Tagline")}</Label>
          <Input value={tagline} maxLength={60} onChange={(e) => onTagline(e.target.value)} /></label>
      </div>
      <div>
        <Label hint={t("1 hingga 5, setiap satu dengan gambar sendiri; nama dan manfaat pilihan (kosong = papan cerita tulis dari idea)", "1 to 5, each with its own picture; name and benefits optional (empty = the storyboard writes them from the idea)")}>{t("Produk", "Products")}</Label>
        <ul className="space-y-2">
          {products.map((p, i) => (
            <li key={p.media_id || p.ref?.path || i} className="flex items-start gap-2" data-motion-product>
              <div className="h-16 w-12 flex-none rounded-tile border border-line bg-white bg-contain bg-center bg-no-repeat" style={p.thumb ? { backgroundImage: `url(${p.thumb})` } : undefined} />
              <div className="grid min-w-0 flex-1 gap-1 sm:grid-cols-2">
                <Input value={p.name} maxLength={60} onChange={(e) => set(i, { name: e.target.value })} placeholder={t("Nama produk", "Product name")} aria-label={t("Nama produk", "Product name")} />
                <Input value={p.benefits} maxLength={120} onChange={(e) => set(i, { benefits: e.target.value })} placeholder={t("Manfaat: Ringan · Tanpa pewangi", "Benefits: Light · Fragrance free")} aria-label={t("Manfaat", "Benefits")} />
              </div>
              <Button size="sm" variant="ghost" onClick={() => onProducts(products.filter((_, k) => k !== i))} aria-label={t("Buang produk", "Remove product")}><Trash2 size={12} /></Button>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="ghost" disabled={full} onClick={() => setPicking(true)}><ImagePlus size={12} /> {t("Pilih dari pustaka gambar", "Pick from the image library")}</Button>
          <label className={`inline-flex cursor-pointer items-center gap-1 rounded-pill bg-surface-2 px-3 py-1.5 text-xs ${full || !owned || uploading || !user?.id ? "pointer-events-none opacity-50" : ""}`}>
            {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />} {t("Muat naik gambar produk", "Upload a product picture")}
            <input type="file" className="hidden" accept="image/png,image/jpeg,image/webp" onChange={upload} disabled={full || !owned || uploading || !user?.id} aria-label={t("Muat naik gambar produk", "Upload a product picture")} /></label>
          <label className="flex items-center gap-1 text-[11px] text-muted"><input type="checkbox" checked={owned} onChange={(e) => setOwned(e.target.checked)} /> {t("Gambar produk ini milik saya", "These product pictures are mine")}</label>
        </div>
        {error && <p role="alert" className="mt-1 text-xs text-danger">{error}</p>}
      </div>
      <Modal open={picking} onClose={() => setPicking(false)} title={t("Pilih gambar produk", "Pick a product picture")} wide>
        {mediaT.loading && <p className="text-xs text-muted"><Loader2 size={12} className="mr-1 inline animate-spin" />{t("Memuatkan…", "Loading…")}</p>}
        {!mediaT.loading && !library.length && <p className="text-xs text-muted">{t("Tiada gambar siap dalam pustaka. Muat naik di halaman Gambar, atau terus di sini.", "No finished pictures in the library. Upload on the Image page, or straight here.")}</p>}
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8">
          {library.map((pic) => (
            <button key={pic.id} type="button" onClick={() => pick(pic)} title={pic.label} className="aspect-square overflow-hidden rounded-tile border border-line bg-white hover:border-accent">
              <img src={pic.url} alt={pic.label} loading="lazy" className="h-full w-full object-contain" /></button>
          ))}
        </div>
      </Modal>
    </div>
  );
}

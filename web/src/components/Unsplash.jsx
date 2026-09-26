import { useState } from "react";
import { Check, Loader2, Search } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import { Input, Select } from "./ui/Field";

/* Unsplash as a picture source (Wan, 26 Sep 2026: "add also unsplashed choice so image can create from there").
   The page never holds the Unsplash key: a search is a media row the worker answers (backend/semasa/unsplash.py,
   about a minute), a pick is the same row sent back with the chosen photo. The results shown are Unsplash's own
   addresses, and the photographer is credited with a link wherever the photo is shown, per Unsplash's API rules. */

export const isUnsplash = (row) => (row?.provider || "") === "unsplash";

export function UnsplashSearch({ user, postId = null, ideaId = null, stream = "regulab", onQueued, onToast, compact = false }) {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [orientation, setOrientation] = useState(stream === "linkedin" ? "portrait" : "squarish");
  const [busy, setBusy] = useState(false);

  async function go(e) {
    e?.preventDefault?.();
    if (!q.trim()) return;
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.media).insert({
      mode: "prompt", type: "image", provider: "unsplash", prompt: q.trim(), status: "pending", created_by: user.id,
      post_id: postId, idea_id: ideaId, meta: { flow: "unsplash", orientation, alt: q.trim() },
    }).select("id").single();
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    onToast(t("Carian dihantar. Gambar muncul dalam kira-kira seminit.", "Search sent. Photos appear in about a minute."), "ok");
    onQueued?.(data.id);
  }

  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "" : "rounded-tile bg-surface-2/40 p-2.5"}`}>
      <span className="text-[12px] font-medium">Unsplash</span>
      <div className="min-w-0 flex-1 basis-56">
        <Input value={q} onChange={(e) => setQ(e.target.value)} maxLength={120}
          onKeyDown={(e) => { if (e.key === "Enter") go(e); }}
          placeholder={t("Cari foto (Inggeris lebih tepat), cth: cosmetic laboratory", "Search photos, e.g. cosmetic laboratory")}
          aria-label={t("Cari di Unsplash", "Search Unsplash")} /></div>
      <Select value={orientation} onChange={setOrientation} aria-label={t("Orientasi", "Orientation")}
        options={[["squarish", t("Segi empat", "Square")], ["portrait", t("Potret", "Portrait")], ["landscape", t("Landskap", "Landscape")]]} />
      <Button type="button" size="sm" disabled={busy || !q.trim()} onClick={go}>
        {busy ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />} {t("Cari", "Search")}</Button>
    </div>
  );
}

export async function pickUnsplash(row, photoId) {
  const { data, error } = await supabase.from(TABLES.media)
    .update({ status: "pending", attempts: 0, error: null, meta: { ...(row.meta || {}), pick: photoId } })
    .eq("id", row.id).select("id");
  if (error) throw new Error(errText(error));
  if (!data?.length) throw new Error("the search was not updated (0 rows): it may have been deleted");
}

export function UnsplashCredit({ row, className = "" }) {
  const { t } = useLang();
  const c = row?.meta?.credit;
  if (!c?.name) return null;
  return (
    <p className={`[overflow-wrap:anywhere] text-[11px] text-muted ${className}`}>
      {t("Foto oleh", "Photo by")} <a href={c.profile} target="_blank" rel="noopener noreferrer" className="underline">{c.name}</a>{" "}
      {t("di", "on")} <a href={c.page || "https://unsplash.com/?utm_source=semasa&utm_medium=referral"} target="_blank" rel="noopener noreferrer" className="underline">Unsplash</a>
    </p>
  );
}

/* One search row, whatever state it is in: searching, the photos to choose from, the chosen photo, or the error. */
export function UnsplashResults({ row, onPicked, onToast, chosenId = null }) {
  const { t } = useLang();
  const [busy, setBusy] = useState("");
  if (!row) return null;
  const m = row.meta || {};
  if (row.status === "pending" || row.status === "processing") {
    return (
      <p className="flex items-center gap-1.5 p-3 text-[12px] text-muted"><Loader2 size={12} className="animate-spin" />
        {m.pick ? t("Mengambil foto dipilih…", "Fetching the chosen photo…") : t("Mencari di Unsplash: “{q}”…", "Searching Unsplash: “{q}”…", { q: row.prompt })}</p>
    );
  }
  if (row.status === "error") {
    return <p className="m-3 [overflow-wrap:anywhere] rounded-tile bg-danger/5 p-2 text-[12px] text-danger">{row.error}</p>;
  }
  if (row.generated_media_url) {
    return (
      <div>
        <img src={row.generated_media_url} alt={m.alt || row.prompt} loading="lazy" className="w-full object-cover" />
        <UnsplashCredit row={row} className="px-3 pt-2" />
      </div>
    );
  }
  const results = m.results || [];
  if (!results.length) return <p className="p-3 text-[12px] text-muted">{t("Tiada foto untuk “{q}”. Cuba perkataan lain (Inggeris).", "No photos for “{q}”. Try other words.", { q: row.prompt })}</p>;

  async function pick(p) {
    setBusy(p.id);
    try { await pickUnsplash(row, p.id); onPicked?.(row.id, p); onToast?.(t("Dipilih. Foto disimpan dalam seminit.", "Chosen. The photo is stored within a minute."), "ok"); }
    catch (e) { onToast?.(e.message, "danger"); }
    setBusy("");
  }

  return (
    <div className="p-2">
      <p className="px-1 pb-1.5 text-[11px] text-muted">{t("“{q}” · {n} foto · klik untuk pilih", "“{q}” · {n} photos · click one to use it", { q: row.prompt, n: results.length })}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 lg:gap-1.5">
        {results.map((p) => (
          <figure key={p.id} className="min-w-0">
            <button type="button" onClick={() => pick(p)} disabled={!!busy} title={p.alt || p.name}
              className={`relative block w-full overflow-hidden rounded-tile border ${chosenId === p.id ? "border-accent ring-2 ring-accent/40" : "border-line hover:border-accent"}`}
              style={{ aspectRatio: "1 / 1", background: p.color || undefined }}>
              <img src={p.thumb} alt={p.alt || ""} loading="lazy" className="h-full w-full object-cover" />
              {busy === p.id && <span className="absolute inset-0 grid place-items-center bg-ink/40 text-bg"><Loader2 size={16} className="animate-spin" /></span>}
              {chosenId === p.id && <span className="absolute right-1 top-1 rounded-full bg-accent p-0.5 text-bg"><Check size={11} /></span>}
            </button>
            <figcaption className="min-w-0 pt-0.5 text-[11px] text-muted lg:text-[10px]">
              <a href={p.profile} target="_blank" rel="noopener noreferrer" className="block truncate hover:underline">{p.name}</a></figcaption>
          </figure>
        ))}
      </div>
      <p className="px-1 pt-1.5 text-[10px] text-muted">{t("Foto dari", "Photos from")} <a href="https://unsplash.com/?utm_source=semasa&utm_medium=referral" target="_blank" rel="noopener noreferrer" className="underline">Unsplash</a></p>
    </div>
  );
}

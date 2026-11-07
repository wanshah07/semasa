import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { fadeUp } from "../design/motion";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { genActions, lockedMedia, thumbOf } from "../lib/genActions";
import GenerationGallery from "../components/GenerationGallery";
import TileGrid from "../components/TileGrid";
import { Segmented } from "../components/ui/Field";

/* Image library (Wan, 11 Oct 2026: image and video apart, a library of its own, compact, 8 tiles a row). Every picture job
   except a Fragrance ad, a poster (those are in the Poster library) and a video. A tile opens the same card the old Media tab
   drew: retry, delete, open the file. */
export const isImageJob = (r) => r.mode !== "fragrance" && r.type !== "video" && !r.meta?.design;
const RUNNING = ["pending", "processing"];

export function jobLabel(r, t) {
  if (r.mode === "slides") return t("Slaid carousel", "Carousel slides");
  if (r.mode === "upload") return r.meta?.name || t("Gambar anda sendiri", "Your own picture");
  return r.prompt || "";
}

export default function ImageLibraryTab({ user, gens, posts, onToast, go }) {
  const { t } = useLang();
  const [show, setShow] = useState("all");
  const locked = useMemo(() => lockedMedia(posts), [posts]);
  const actions = genActions({ gens, onToast, t });
  const all = useMemo(() => (gens.rows || []).filter(isImageJob), [gens.rows]);
  const rows = all.filter((r) => show === "all" || (show === "running" ? RUNNING.includes(r.status) : r.status === show));
  const count = (k) => all.filter((r) => (k === "running" ? RUNNING.includes(r.status) : r.status === k)).length;
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[13px] font-semibold text-accent">{t("Imej", "Image")}</p>
          <h1 className="mt-2 text-4xl leading-tight">{t("Pustaka imej", "Image library")}</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">{t("Setiap gambar yang dijana, dimuat naik atau dipilih dari Unsplash. Klik satu untuk buka kad penuh: cuba lagi, padam, buka fail.",
            "Every picture generated, uploaded or picked from Unsplash. Click one to open the full card: retry, delete, open the file.")}
          {go && <> <button type="button" className="text-accent underline" onClick={() => go("media")}>{t("Jana imej baharu", "Generate a new image")}</button></>}</p>
        </div>
        <Segmented value={show} onChange={setShow} options={[["all", `${t("Semua", "All")} ${all.length}`], ["done", `${t("Siap", "Done")} ${count("done")}`],
          ["running", `${t("Berjalan", "Running")} ${count("running")}`], ["error", `${t("Gagal", "Failed")} ${count("error")}`]]} />
      </motion.div>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <TileGrid items={rows.map((r) => ({ id: r.id, kind: "image", src: thumbOf(r), status: r.status === "done" ? "" : r.status,
        label: jobLabel(r, t), sub: `${r.provider || t("Tiada", "None")} · ${timeAgo(r.created_at)}` }))}
        detail={(it) => { const r = rows.find((x) => x.id === it.id); return r ? <GenerationGallery rows={[r]} user={user} onToast={onToast} locked={locked} {...actions} /> : null; }}
        empty={t("Tiada gambar untuk paparan ini.", "No pictures for this view.")} />
    </main>
  );
}

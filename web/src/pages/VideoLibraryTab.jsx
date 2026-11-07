import { useMemo } from "react";
import { motion } from "framer-motion";
import { fadeUp } from "../design/motion";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { genActions, lockedMedia, thumbOf } from "../lib/genActions";
import GenerationGallery from "../components/GenerationGallery";
import MotionLab from "../components/MotionLab";
import TileGrid from "../components/TileGrid";

/* Video library (Wan, 11 Oct 2026): every video in one place, compact, 8 tiles a row. Two shelves, because they come from two
   tables: AI clips (the generation jobs, YouTube clips included) and Motion films. A tile opens the full card of its own kind. */
export const isVideoJob = (r) => r.mode !== "fragrance" && r.type === "video";

export default function VideoLibraryTab({ user, gens, posts, onToast, go }) {
  const { t } = useLang();
  const locked = useMemo(() => lockedMedia(posts), [posts]);
  const actions = genActions({ gens, onToast, t });
  const clips = useMemo(() => (gens.rows || []).filter(isVideoJob), [gens.rows]);
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6">
        <p className="text-[13px] font-semibold text-accent">Video</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Pustaka video", "Video library")}</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">{t("Filem Motion dan klip video AI di satu tempat. Klik satu untuk buka kad penuh: main, muat turun, buat semula, jadikan post.",
          "Motion films and AI video clips in one place. Click one to open the full card: play, download, remake, make it a post.")}
        {go && <> <button type="button" className="text-accent underline" onClick={() => go("video")}>{t("Jana video baharu", "Generate a new video")}</button></>}</p>
      </motion.div>

      <h2 className="mb-3 font-display text-xl">Motion</h2>
      <MotionLab user={user} onToast={onToast} view="library" />

      <h2 className="mb-3 mt-10 font-display text-xl">{t("Klip video AI", "AI video clips")}</h2>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <TileGrid items={clips.map((r) => ({ id: r.id, kind: "video", src: r.status === "done" ? thumbOf(r) : "", status: r.status === "done" ? "" : r.status,
        label: r.prompt || t("Klip video", "Video clip"), sub: `${r.provider || t("Tiada", "None")} · ${timeAgo(r.created_at)}` }))}
        detail={(it) => { const r = clips.find((x) => x.id === it.id); return r ? <GenerationGallery rows={[r]} user={user} onToast={onToast} locked={locked} {...actions} /> : null; }}
        empty={t("Belum ada klip video AI.", "No AI video clips yet.")} />
    </main>
  );
}

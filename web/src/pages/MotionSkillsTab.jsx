import { motion } from "framer-motion";
import { fadeUp } from "../design/motion";
import { useLang } from "../lib/i18n";
import MotionLab from "../components/MotionLab";
import MotionSkill from "../components/MotionSkill";

/* Motion skills, all in one place (Wan, 11 Oct 2026: "make sure motion skill in one place including place to upload"):
   Wan's own instructions for every motion film (a .md or .txt file can be uploaded into it) and the motion repos that give
   a film a different look. The effect library and the pictures for one film stay in the Motion form, because they are
   choices for that film rather than something kept. */
export default function MotionSkillsTab({ user, settings, save, onToast }) {
  const { t } = useLang();
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6">
        <p className="text-[13px] font-semibold text-accent">Video</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Kemahiran motion", "Motion skills")}</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">{t("Semua yang mengajar video motion cara menulis: arahan anda sendiri dan repo gaya. Muat naik fail kemahiran di sini; pilih gaya di borang Jana video.",
          "Everything that teaches the motion video how to write: your own instructions and the style repos. Upload a skill file here; pick a style in the Generate video form.")}</p>
      </motion.div>
      <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
        <MotionSkill settings={settings} save={save} onToast={onToast} />
        <MotionLab user={user} onToast={onToast} view="skills" />
      </div>
    </main>
  );
}

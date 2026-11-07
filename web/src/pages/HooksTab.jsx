import { motion } from "framer-motion";
import { fadeUp } from "../design/motion";
import { useLang } from "../lib/i18n";
import HookStyles from "../components/HookStyles";
import HookLearning from "../components/HookLearning";

/* Bank hook (Wan, 11 Oct 2026, Phase 4: "hooks bank boleh edit, add, apply"). One page for everything that decides a post's first
   line: the built-in 25 (see them, copy them to edit), Wan's own hook sets (written by hand, copied, or made by the bot from
   screenshots: edited, added to and applied as the default or on one idea), and what has earned views and interaction so far.
   Moved here from Tetapan. */
export default function HooksTab({ settings, save, onToast }) {
  const { t } = useLang();
  return (
    <main className="mx-auto max-w-page space-y-6 px-4 pb-20 pt-10 sm:px-6" data-hooks-page>
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <h1 className="font-display text-3xl">{t("Bank hook", "Hooks bank")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t("Baris pertama setiap post dan setiap filem dibina atas satu bentuk hook. Pilih set yang dipakai, ubah dan tambah bentuknya, atau pilih set lain untuk satu idea sahaja semasa membuat idea.",
          "Every post's and every film's first line is built on a hook shape. Choose the set in use, edit and add to its shapes, or pick another set for one idea when you make it.")}</p>
      </motion.div>
      <HookStyles settings={settings} save={save} onToast={onToast} />
      <HookLearning settings={settings} save={save} onToast={onToast} />
    </main>
  );
}

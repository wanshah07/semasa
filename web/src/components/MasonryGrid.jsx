import { motion } from "framer-motion";
import { stagger } from "../design/motion";
import { useLang } from "../lib/i18n";
import Skeleton from "./ui/Skeleton";
import TrendCard from "./TrendCard";

export default function MasonryGrid({ rows, loading, onCategory, onIdea, onFaq }) {
  const { t } = useLang();
  if (loading) {
    return (
      <div className="masonry">
        {Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} style={{ height: 120 + (i % 3) * 40 }} />)}
      </div>
    );
  }
  if (!rows.length) {
    return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Tiada isu sepadan.", "No matching issues.")}</p>;
  }
  return (
    <motion.div className="masonry" variants={stagger(0.03)} initial="hidden" animate="show">
      {rows.map((row) => <TrendCard key={row.id} row={row} onCategory={onCategory} onIdea={onIdea} onFaq={onFaq} />)}
    </motion.div>
  );
}

import { motion } from "framer-motion";
import { ExternalLink, Flame, Lightbulb } from "lucide-react";
import { fadeUp } from "../design/motion";
import { hostOf, stampMYT, timeAgo } from "../lib/format";
import Card from "./ui/Card";
import CategoryBadge from "./ui/CategoryBadge";

export default function TrendCard({ row, onCategory, onIdea }) {
  const trending = (row.tags || []).find((t) => t.startsWith("carian:"));
  const traffic = (row.tags || []).find((t) => t.startsWith("trafik:"));
  const when = row.published_at || row.created_at;
  return (
    <motion.div variants={fadeUp} layout>
      <Card as="article" className="group overflow-hidden transition duration-300 ease-out hover:-translate-y-0.5 hover:shadow-lift">
        <div className="flex items-center justify-between gap-2 px-4 pt-4">
          <CategoryBadge category={row.category} onClick={onCategory ? () => onCategory(row.category) : undefined} />
          <time className="text-[11px] text-muted" title={stampMYT(when)}>{timeAgo(when)}</time>
        </div>
        <a href={row.url} target="_blank" rel="noopener noreferrer" className="block px-4 pb-4 pt-3">
          <h3 className="font-display text-[17px] leading-snug text-ink group-hover:text-accent">{row.title}</h3>
          {row.summary && (
            <p className="mt-2 text-sm leading-relaxed text-muted">{row.summary}</p>
          )}
          {trending && (
            <p className="mt-3 inline-flex items-center gap-1.5 rounded-pill bg-warm/40 px-2.5 py-1 text-[11px] font-medium text-ink">
              <Flame size={12} /> {trending.slice(7)} {traffic ? `· ${traffic.slice(7)}` : ""}
            </p>
          )}
          <div className="mt-3 flex items-center justify-between text-[11px] text-muted">
            <span className="truncate">{row.source}{hostOf(row.url) && !hostOf(row.url).includes("google") ? ` · ${hostOf(row.url)}` : ""}</span>
            <span className="flex items-center gap-1.5">
              {row.summary_source === "llm" && <span className="rounded-pill bg-accent/10 px-1.5 py-0.5 text-[10px] text-accent">AI</span>}
              <span className="uppercase">{row.lang}</span>
              <ExternalLink size={11} />
            </span>
          </div>
        </a>
        {onIdea && (
          <div className="border-t border-line/70 px-4 py-2">
            <button type="button" onClick={() => onIdea(row)}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-accent hover:underline">
              <Lightbulb size={13} /> Jadikan idea
            </button>
          </div>
        )}
      </Card>
    </motion.div>
  );
}

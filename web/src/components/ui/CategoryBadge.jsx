import { CATEGORY_LABEL } from "../../lib/format";

/* Colour comes from --cat-<category> in tokens.css; the component knows no hex. */
export default function CategoryBadge({ category, active = false, onClick, size = "sm" }) {
  const c = `var(--cat-${category || "lain"})`;
  const pad = size === "sm" ? "px-2.5 py-0.5 text-[11px]" : "px-3 py-1 text-xs";
  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-pill font-semibold tracking-wide uppercase transition ${pad}`}
      style={{
        color: active ? `rgb(var(--c-accent-ink))` : `rgb(${c})`,
        background: active ? `rgb(${c})` : `rgb(${c} / 0.12)`,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: active ? "currentColor" : `rgb(${c})` }} />
      {CATEGORY_LABEL[category] || category}
    </Tag>
  );
}

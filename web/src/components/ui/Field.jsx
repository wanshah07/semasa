import { useLang } from "../../lib/i18n";

/* Small form primitives so every screen reads the same. */
export function Label({ children, hint }) {
  return (
    <span className="mb-1 block text-xs font-medium text-muted">
      {children}{hint && <span className="ml-1 font-normal opacity-80">· {hint}</span>}
    </span>
  );
}

export function Select({ value, onChange, options, className = "", ...rest }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} {...rest}
      className={`rounded-pill border border-line bg-surface px-3 py-2 text-xs text-ink outline-none focus:border-accent ${className}`}>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );
}

export function TextArea({ className = "", ...rest }) {
  return <textarea {...rest} className={`w-full resize-y rounded-tile border border-line bg-bg p-3 text-sm outline-none focus:border-accent ${className}`} />;
}

export function Input({ className = "", ...rest }) {
  return <input {...rest} className={`w-full rounded-pill border border-line bg-bg px-4 py-2 text-sm outline-none focus:border-accent ${className}`} />;
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-pill bg-surface-2 p-1 text-xs" role="radiogroup">
      {options.map(([v, l]) => (
        <button type="button" key={v} role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={`rounded-pill px-3 py-1.5 ${value === v ? "bg-surface text-ink shadow-card" : "text-muted"}`}>{l}</button>
      ))}
    </div>
  );
}

export function Modal({ open, onClose, title, children }) {
  const { t } = useLang();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 pt-16" onClick={onClose}>
      <div className="w-full max-w-lg rounded-card border border-line bg-surface p-5 shadow-lift" onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label={title}>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-lg">{title}</h3>
          <button type="button" onClick={onClose} className="text-sm text-muted hover:text-ink" aria-label={t("Tutup", "Close")}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

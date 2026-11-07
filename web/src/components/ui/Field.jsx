import { useLang } from "../../lib/i18n";

/* Small form primitives so every screen reads the same. */
export function Label({ children, hint }) {
  return (
    <span className="mb-1 block text-xs font-medium text-muted">
      {children}{hint && <span className="ml-1 font-normal opacity-90">· {hint}</span>}
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
    <div className="inline-flex max-w-full flex-wrap rounded-pill bg-surface-2 p-1 text-xs" role="radiogroup">
      {options.map(([v, l]) => (
        <button type="button" key={v} role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={`rounded-pill px-3 py-1.5 ${value === v ? "bg-surface text-ink shadow-card" : "text-muted"}`}>{l}</button>
      ))}
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide = false }) {
  const { t } = useLang();
  if (!open) return null;
  return (
    // close only when the press starts on the backdrop too: selecting text and letting go outside must not lose an edit
    // on a phone the dialog is the whole screen (a floating card under the notch left a sliver to tap and scroll in);
    // from sm up it is the centred card it always was
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-0 sm:p-4 sm:pt-16"
      onMouseDown={(e) => { e.currentTarget.dataset.down = e.target === e.currentTarget ? "1" : ""; }}
      onClick={(e) => { if (e.target === e.currentTarget && e.currentTarget.dataset.down === "1") onClose(); }}>
      <div className={`min-h-full w-full ${wide ? "max-w-3xl" : "max-w-lg"} rounded-none border-0 border-line bg-surface p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-[max(1.25rem,env(safe-area-inset-top))] shadow-lift sm:min-h-0 sm:rounded-card sm:border sm:p-5`} onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label={title}>
        <div className="sticky top-0 z-10 -mx-5 -mt-2 mb-3 flex items-center justify-between gap-3 bg-surface px-5 pt-2 sm:static sm:mx-0 sm:mt-0 sm:px-0 sm:pt-0">
          <h3 className="text-lg">{title}</h3>
          <button type="button" onClick={onClose} className="-mr-2 grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-ink" aria-label={t("Tutup", "Close")}>✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

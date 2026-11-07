import { useEffect } from "react";
import { IconChevronLeft, IconX } from "@tabler/icons-react";
import { useLang } from "../../lib/i18n";

/* A panel on a phone (pages/ChatTab.jsx: model picker, history, pinned memory). On a phone a floating card leaves a sliver of
   page to tap and scroll behind it and puts the close button under the notch, so here a sheet is the whole screen with a Back
   button (`variant="full"`), or a bottom sheet that rises over the page (`variant="bottom"`, for a short list such as the model
   picker). From sm (640 px) up it is a centred card. Escape and a press on the backdrop close it; the page behind cannot scroll
   while it is open. The press has to START on the backdrop: letting go outside after selecting text must not close it. */
export default function Sheet({ open, onClose, title, children, variant = "full", wide = false, footer = null }) {
  const { t } = useLang();
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);
  if (!open) return null;
  const bottom = variant === "bottom";
  return (
    <div className={`fixed inset-0 z-50 flex bg-ink/40 ${bottom ? "items-end justify-center sm:items-center sm:p-4" : "items-stretch justify-center sm:items-start sm:p-4 sm:pt-16"}`}
      data-sheet={variant}
      onMouseDown={(e) => { e.currentTarget.dataset.down = e.target === e.currentTarget ? "1" : ""; }}
      onClick={(e) => { if (e.target === e.currentTarget && e.currentTarget.dataset.down === "1") onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}
        className={`flex w-full flex-col bg-surface shadow-lift ${wide ? "sm:max-w-2xl" : "sm:max-w-lg"} ${
          bottom ? "max-h-[88svh] rounded-t-card pb-[env(safe-area-inset-bottom,0px)] sm:max-h-[80vh] sm:rounded-card"
            : "h-full pt-[env(safe-area-inset-top,0px)] sm:h-auto sm:max-h-[85vh] sm:rounded-card"}`}>
        {bottom && <div aria-hidden className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-line sm:hidden" />}
        <div className="flex shrink-0 items-center gap-1 border-b border-line px-2 py-1.5 sm:px-4">
          {!bottom && (
            <button type="button" onClick={onClose} aria-label={t("Kembali", "Back")}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-ink transition hover:bg-surface-2 active:bg-surface-2 sm:hidden">
              <IconChevronLeft size={22} />
            </button>
          )}
          <h3 className="min-w-0 flex-1 truncate px-1 text-base sm:text-lg">{title}</h3>
          <button type="button" onClick={onClose} aria-label={t("Tutup", "Close")}
            className={`grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-ink active:bg-surface-2 ${bottom ? "" : "hidden sm:grid"}`}>
            <IconX size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 sm:px-4" style={{ WebkitOverflowScrolling: "touch" }}>{children}</div>
        {footer && <div className="shrink-0 border-t border-line px-3 py-2 sm:px-4">{footer}</div>}
      </div>
    </div>
  );
}

/* The notification cards Wan pasted (11 Nov 2026), as a component the app can feed: a card per notice with an icon by kind,
   a title, an optional body and an optional dismiss button. The pasted file was a full-screen demo holding its own sample
   notices; here the notices come in as props. Its `text-success` / `text-warning` colours were fixed oklch values with a
   `.dark` variant; Semasa has many themes and no `.dark` class, so the accents are the theme's own ok / warn / danger and
   the card is the theme's surface and ink, readable on every theme. Used by components/Toast.jsx. */
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type NoticeVariant = "success" | "info" | "warning" | "error";
export interface Notice { id: string | number; variant?: NoticeVariant; title: string; body?: string }

const config: Record<NoticeVariant, { icon: typeof CircleCheck; accent: string }> = {
  success: { icon: CircleCheck, accent: "text-ok" },
  info: { icon: Info, accent: "text-ink" },
  warning: { icon: TriangleAlert, accent: "text-warn" },
  error: { icon: CircleAlert, accent: "text-danger" },
};

export function NoticeCard({ notice, onDismiss, dismissLabel = "Dismiss", className }: {
  notice: Notice; onDismiss?: (id: Notice["id"]) => void; dismissLabel?: string; className?: string;
}) {
  const { icon: Icon, accent } = config[notice.variant || "info"];
  return (
    <div role="status" className={cn("flex w-full items-start gap-3 rounded-tile border border-line bg-surface p-3 text-left text-ink shadow-lift", className)}>
      <Icon className={cn("mt-0.5 size-5 shrink-0", accent)} aria-hidden="true" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-semibold [overflow-wrap:anywhere]">{notice.title}</span>
        {notice.body && <span className="text-xs text-muted [overflow-wrap:anywhere]">{notice.body}</span>}
      </div>
      {onDismiss && (
        <button type="button" onClick={() => onDismiss(notice.id)} aria-label={dismissLabel}
          className="-m-2 grid h-10 w-10 shrink-0 place-items-center rounded-full text-muted transition-colors hover:text-ink">
          <X className="size-4" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

export default function NotificationsBlock({ notices, onDismiss, empty, dismissLabel, className }: {
  notices: Notice[]; onDismiss?: (id: Notice["id"]) => void; empty?: string; dismissLabel?: string; className?: string;
}) {
  return (
    <div className={cn("flex w-full max-w-sm flex-col gap-3", className)}>
      {notices.map((n) => <NoticeCard key={n.id} notice={n} onDismiss={onDismiss} dismissLabel={dismissLabel} />)}
      {notices.length === 0 && empty && (
        <p className="rounded-tile border border-dashed border-line py-10 text-center text-sm text-muted">{empty}</p>
      )}
    </div>
  );
}

import { useMemo } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, CreditCard, FileText, Lightbulb, Send, Wallet } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { stampMYT } from "../lib/format";
import { dayNames } from "../lib/brand";
import { fmtDate, money, summary } from "../lib/billing";
import { domainsOn, dowOf, myt, refOf, slotsOf } from "../lib/slots";
import { subsSummary, upcoming } from "../lib/subscriptions";
import { POST_PROGRESS, nextInQueue, recentActivity, systemStats, weeklyPosts } from "../lib/dashboard";
import { AREAS, titleOf } from "./LogTab";
import { CYCLE_WORDS } from "./SubscriptionsTab";
import App1 from "@/components/ui/app-1";
import { GradientBackground } from "@/components/ui/gradient-backgrounds";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/app-1-utils/card";
import Button from "../components/ui/Button";

/* Papan: the whole system on one page (Wan, 9 Oct 2026: "yes whole system dashboard"). Everything is computed from
   rows the page already loads (ideas, posts, the publish log, the log, the Bil documents and the subscriptions) with
   lib/dashboard.js; nothing here writes. The hero band is components/ui/gradient-backgrounds.tsx. */

const POST_WORDS = { draft: ["Draf", "Draft"], approved: ["Diluluskan", "Approved"], scheduled: ["Dijadual", "Scheduled"], posted: ["Disiar", "Posted"] };
const DOMAIN_WORDS = {
  kosmetik: "Kosmetik", kajian_kes: ["Kajian kes", "Case study"], sains_kosmetik: ["Sains kosmetik", "Cosmetic science"], halal_my: "Halal",
  fatwa: "Fatwa", farmaseutikal: ["Farmaseutikal", "Pharma"], makanan: ["Makanan", "Food"],
};

export default function HomeTab({ ideas, posts, log, activity, brand, go, user }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const docsT = useTable(TABLES.billingDocs, { enabled: true, limit: 2000, realtime: false });
  const subsT = useTable(TABLES.subscriptions, { enabled: true, order: "next_payment", ascending: true, limit: 500, realtime: false });
  const now = myt();
  const today = now.date;
  const stats = useMemo(() => systemStats({ ideas: ideas.rows, posts: posts.rows, log: log.rows, today }), [ideas.rows, posts.rows, log.rows, today]);
  const weekly = useMemo(() => weeklyPosts(posts.rows, log.rows, today, 8), [posts.rows, log.rows, today]);
  const bil = useMemo(() => summary(docsT.rows, today), [docsT.rows, today]);
  const subs = useMemo(() => subsSummary(subsT.rows, today), [subsT.rows, today]);
  const due = useMemo(() => upcoming(subsT.rows, today, 30).slice(0, 6), [subsT.rows, today]);
  const queue = useMemo(() => nextInQueue(posts.rows, today, 6), [posts.rows, today]);
  const recent = useMemo(() => recentActivity(activity.rows, 12), [activity.rows]);
  const todaysDomains = domainsOn(brand, today);
  const hour = Number(now.time.slice(0, 2));
  const greet = hour < 12 ? t("Selamat pagi", "Good morning") : hour < 19 ? t("Selamat petang", "Good afternoon") : t("Selamat malam", "Good evening");
  const name = (user?.user_metadata?.full_name || user?.email || "Wan").split(/[\s@]/)[0];

  const projects = queue.map((p) => ({
    id: p.id, name: `${refOf(p, brand)} · ${p.hook || p.title || t("(tiada tajuk)", "(untitled)")}`.slice(0, 90),
    description: `${fmtDate(p.date)} ${p.slot || ""} · ${p.stream === "linkedin" ? "LinkedIn" : "ws.regulab"}${p.domain ? ` · ${w(DOMAIN_WORDS[p.domain] || p.domain)}` : ""}`,
    progress: POST_PROGRESS[p.status] ?? 0, status: w(POST_WORDS[p.status] || [p.status, p.status]),
    badge: p.status === "scheduled" ? "default" : p.status === "approved" ? "secondary" : "outline", team: [], onClick: () => go("post", p.id),
  }));
  const activityRows = recent.map((r) => {
    const area = AREAS[r.area] || { label: r.area, en: r.area };
    return { id: r.id, person: { name: L ? area.en : area.label, initials: String(r.area || "?").slice(0, 2).toUpperCase() },
      action: titleOf(r.title), time: stampMYT(r.at), onClick: () => go("log") };
  });

  const header = (
    <GradientBackground glow="top" className="mb-2">
      <motion.div {...fadeUp} className="flex flex-wrap items-end justify-between gap-4 p-6 sm:p-8">
        <div>
          <p className="text-[11px] uppercase tracking-widest text-muted">{dayNames()[dowOf(today)]} · {fmtDate(today)} · {now.time} MYT</p>
          <h1 className="mt-1 font-display text-3xl sm:text-4xl">{greet}, {name}.</h1>
          <p className="mt-2 max-w-2xl text-sm text-ink/80">
            {todaysDomains.length
              ? t("Hari ini ws.regulab menyiarkan {d} pada {s}. LinkedIn: {l}.", "Today ws.regulab posts {d} at {s}. LinkedIn: {l}.",
                { d: todaysDomains.map((d) => w(DOMAIN_WORDS[d] || d)).join(" + "), s: slotsOf(brand, "regulab").join(" · "), l: slotsOf(brand, "linkedin").join(" · ") })
              : t("Hari ini bukan hari siaran ws.regulab. LinkedIn: {l}.", "ws.regulab does not post today. LinkedIn: {l}.", { l: slotsOf(brand, "linkedin").join(" · ") })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => go("idea")}><Lightbulb size={14} /> {t("Idea", "Ideas")} {stats.ideasNew ? `(${stats.ideasNew})` : ""}</Button>
          <Button variant="ghost" onClick={() => go("post")}><FileText size={14} /> {t("Post", "Posts")} {stats.drafts ? `(${stats.drafts})` : ""}</Button>
          <Button onClick={() => go("isu")}>{t("Isu semasa", "Current issues")}</Button>
        </div>
      </motion.div>
    </GradientBackground>
  );

  const aside = (
    <Card>
      <CardHeader>
        <CardTitle>{t("Langganan akan datang", "Upcoming subscriptions")}</CardTitle>
        <CardDescription>{t("30 hari seterusnya · {m} sebulan (anggaran)", "Next 30 days · {m} a month (estimate)", { m: money(subs.monthly, { currency: "MYR" }) })}</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="flex flex-col gap-2">
          {due.map((s) => {
            const late = s.next_payment < today;
            return (
              <li key={s.id} className="flex items-center justify-between gap-3 text-sm">
                <div className="min-w-0">
                  <p className="truncate">{s.vendor} <span className="text-muted">· {s.name}</span></p>
                  <p className={`text-xs ${late ? "text-danger" : "text-muted"}`}>{fmtDate(s.next_payment)} · {w(CYCLE_WORDS[s.cycle])}{s.auto_pay ? ` · ${t("auto", "auto")}` : ""}</p>
                </div>
                <span className="shrink-0 font-mono text-xs tabular-nums">{money(s.amount, { currency: s.currency })}</span>
              </li>
            );
          })}
          {!due.length && <li className="text-xs text-muted">{/semasa_subscriptions/.test(subsT.error || "")
            ? t("Jalankan supabase/030_subscriptions.sql sekali.", "Run supabase/030_subscriptions.sql once.")
            : t("Tiada bil dalam 30 hari.", "Nothing due in 30 days.")}</li>}
        </ol>
        <Button size="sm" variant="ghost" className="mt-3" onClick={() => go("langganan")}><CreditCard size={13} /> {t("Semua langganan", "All subscriptions")}</Button>
      </CardContent>
    </Card>
  );

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-6 sm:px-6">
      <App1
        header={header}
        keys={{ line: "drafted", area: "published" }}
        stats={[
          { label: t("Idea baharu", "New ideas"), value: String(stats.ideasNew), icon: Lightbulb,
            hint: stats.ideasError ? t("{n} gagal", "{n} failed", { n: stats.ideasError }) : t("{n} sedang ditulis", "{n} being written", { n: stats.ideasWorking }), tone: stats.ideasError ? "danger" : "" },
          { label: t("Draf menunggu", "Drafts waiting"), value: String(stats.drafts), icon: FileText, hint: t("{n} dalam giliran · {d} hari ini", "{n} in the queue · {d} today", { n: stats.queued, d: stats.queuedToday }) },
          { label: t("Disiar minggu ini", "Published this week"), value: String(stats.sentThisWeek), icon: Send, tone: stats.errorsThisWeek ? "danger" : "ok",
            hint: stats.errorsThisWeek ? t("{n} ralat penerbit", "{n} publisher errors", { n: stats.errorsThisWeek }) : t("tiada ralat penerbit", "no publisher errors") },
          { label: t("Belum dijelaskan", "Outstanding"), value: money(bil.outstanding, { currency: "MYR" }), icon: bil.overdueCount ? AlertTriangle : Wallet, tone: bil.overdueCount ? "danger" : "",
            hint: bil.overdueCount ? t("{n} invois lewat · {m}", "{n} invoices overdue · {m}", { n: bil.overdueCount, m: money(bil.overdue, { currency: "MYR" }) }) : t("{n} invois terbuka", "{n} open invoices", { n: bil.outstandingCount }) },
        ]}
        series={weekly}
        formatValue={(n) => String(n)}
        projects={projects}
        activity={activityRows}
        aside={aside}
        words={{
          chartTitle: t("Ditulis lawan disiar", "Drafted against published"), chartDescription: t("Lapan minggu terakhir: post yang ditulis dan post yang sampai ke saluran", "The last eight weeks: posts written and posts that reached a channel"),
          invoiced: t("Ditulis", "Drafted"), paid: t("Disiar", "Published"),
          projectsTitle: t("Seterusnya dalam giliran", "Next in the queue"), projectsDescription: t("Post terdekat dan sejauh mana ia dalam aliran: draf → lulus → jadual → siar", "The nearest posts and how far each is through draft → approved → scheduled → posted"),
          noProjects: t("Tiada post dari hari ini. Pekerja mengisi slot kosong malam ini.", "No posts from today on. The worker fills empty slots tonight."), due: t("Slot", "Slot"),
          activityTitle: t("Aktiviti sistem", "System activity"), activityDescription: t("Log terkini: scrape, idea, post, penerbit", "The latest log lines: scrape, ideas, posts, publisher"),
          noActivity: t("Tiada log lagi.", "No log lines yet."),
        }}
      />
      <p className="mt-4 flex items-center gap-2 text-[11px] text-muted"><CalendarClock size={12} /> {t("Angka dikira dari jadual langsung; muat semula setiap 90 saat.", "Figures come from the live tables and refresh every 90 seconds.")}</p>
    </main>
  );
}

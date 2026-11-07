import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CalendarClock, CreditCard, FileText, LayoutGrid, Lightbulb, Send, Wallet } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { stampMYT } from "../lib/format";
import { dayNames } from "../lib/brand";
import { fmtDate, money, summary } from "../lib/billing";
import { domainsOn, dowOf, myt, refOf, slotsOf } from "../lib/slots";
import { subsSummary, upcoming } from "../lib/subscriptions";
import { POST_PROGRESS, hiddenFrom, nextInQueue, recentActivity, systemStats, visibleWidgets, weeklyPosts } from "../lib/dashboard";
import { AREAS, titleOf } from "./LogTab";
import { CYCLE_WORDS } from "./SubscriptionsTab";
import App1 from "@/components/ui/app-1";
import { AuroraBackground } from "@/components/ui/aurora-background";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/app-1-utils/card";
import Button from "../components/ui/Button";
import AiTeam from "../components/AiTeam";
import { Modal } from "../components/ui/Field";
import { DashboardLayoutConfigurator } from "@/components/ui/dashboard-configuration";
import HomeCharts from "../components/HomeCharts";

/* Papan: the whole system on one page (Wan, 9 Oct 2026: "yes whole system dashboard"). Everything is computed from
   rows the page already loads (ideas, posts, the publish log, the log, the Bil documents and the subscriptions) with
   lib/dashboard.js; nothing here writes. The hero band is components/ui/gradient-backgrounds.tsx. */

const POST_WORDS = { draft: ["Draf", "Draft"], approved: ["Diluluskan", "Approved"], scheduled: ["Dijadual", "Scheduled"], posted: ["Disiar", "Posted"] };
const DOMAIN_WORDS = {
  kosmetik: "Kosmetik", kajian_kes: ["Kajian kes", "Case study"], sains_kosmetik: ["Sains kosmetik", "Cosmetic science"], halal_my: "Halal",
  fatwa: "Fatwa", farmaseutikal: ["Farmaseutikal", "Pharma"], makanan: ["Makanan", "Food"],
};

export default function HomeTab({ ideas, posts, log, activity, brand, go, user, settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const docsT = useTable(TABLES.billingDocs, { enabled: true, limit: 2000, realtime: false });
  const subsT = useTable(TABLES.subscriptions, { enabled: true, order: "next_payment", ascending: true, limit: 500, realtime: false });
  const apiT = useTable(TABLES.apiStatus, { enabled: true, order: "role", ascending: true, limit: 20, realtime: false, everyMs: 300_000 });
  const usageT = useTable(TABLES.apiUsage, { enabled: true, order: "created_at", limit: 2000, realtime: false, everyMs: 300_000 });   // 14 days for the tokens chart
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
  // which widgets show (supabase/065 settings.dashboard): kept here as well, so a tick shows at once and a failed save says why
  const [visible, setVisible] = useState(() => visibleWidgets(settings?.dashboard));
  const layoutKey = JSON.stringify(settings?.dashboard?.hidden || []);
  useEffect(() => { setVisible(visibleWidgets(settings?.dashboard)); }, [layoutKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const [arranging, setArranging] = useState(false);
  const shows = (id) => visible.includes(id);
  async function keepLayout(next) {
    const prev = visible;
    setVisible(visibleWidgets({ hidden: hiddenFrom(next) }));
    try { await save?.("dashboard", { ...(settings?.dashboard || {}), hidden: hiddenFrom(next) }); }
    catch (e) {
      setVisible(prev);
      onToast?.(/not found/.test(e.message) ? t("Jalankan supabase/065_dashboard_layout.sql sekali dahulu.", "Run supabase/065_dashboard_layout.sql once first.") : e.message, "danger");
    }
  }
  const widgetList = [
    { id: "stats", title: t("Angka utama", "Headline figures"), description: t("Idea baharu, draf menunggu, disiar minggu ini, belum dijelaskan. Sentiasa dipapar.", "New ideas, drafts waiting, published this week, outstanding. Always shown."), isPermanent: true },
    { id: "chart", title: t("Ditulis lawan disiar", "Drafted against published"), description: t("Carta lapan minggu.", "The eight-week chart.") },
    { id: "charts", title: t("Carta ringkas", "More charts"), description: t("Idea ikut status, siaran ikut saluran, token AI sehari, post ikut topik.", "Ideas by status, posts by channel, AI tokens a day, posts by topic.") },
    { id: "queue", title: t("Seterusnya dalam giliran", "Next in the queue"), description: t("Post terdekat dan tahap alirannya.", "The nearest posts and how far along they are.") },
    { id: "activity", title: t("Aktiviti sistem", "System activity"), description: t("Log terkini: scrape, idea, post, penerbit.", "The latest log lines: scrape, ideas, posts, publisher.") },
    { id: "ai", title: t("Pasukan AI", "AI team"), description: t("Robot yang menulis sekarang dan status setiap gerbang.", "Which robot writes now and each gateway's state.") },
    { id: "subs", title: t("Langganan akan datang", "Upcoming subscriptions"), description: t("Bil 30 hari seterusnya.", "Bills in the next 30 days.") },
  ];
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
    <AuroraBackground className="mb-2 h-auto w-full items-stretch justify-start overflow-hidden rounded-card border border-line/80 bg-surface text-ink dark:bg-surface">
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="flex flex-wrap items-end justify-between gap-4 p-6 sm:p-8">
        <div>
          <p className="text-xs font-medium text-muted">{dayNames()[dowOf(today)]} · {fmtDate(today)} · {now.time} MYT</p>
          <h1 className="mt-1 font-display text-3xl sm:text-4xl">{greet}, {name}.</h1>
          <p className="mt-2 max-w-2xl text-sm text-ink/80">
            {/* domainsOn is null when the rota names nothing for this weekday, which means "posts, any domain", not "no posting day" */}
            {todaysDomains?.length !== 0
              ? t("Hari ini ws.regulab menyiarkan {d} pada {s}. LinkedIn: {l}.", "Today ws.regulab posts {d} at {s}. LinkedIn: {l}.",
                { d: (todaysDomains || []).map((d) => w(DOMAIN_WORDS[d] || d)).join(" + ") || t("ikut rota", "per the rota"), s: slotsOf(brand, "regulab").join(" · "), l: slotsOf(brand, "linkedin").join(" · ") })
              : t("Hari ini bukan hari siaran ws.regulab. LinkedIn: {l}.", "ws.regulab does not post today. LinkedIn: {l}.", { l: slotsOf(brand, "linkedin").join(" · ") })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* one primary: the drafts waiting for approval when there are any (the gate is the day's real work), else the ideas */}
          <Button variant={stats.drafts ? "ghost" : "primary"} onClick={() => go("idea")}><Lightbulb size={14} /> {t("Idea", "Ideas")} {stats.ideasNew ? `(${stats.ideasNew})` : ""}</Button>
          <Button variant={stats.drafts ? "primary" : "ghost"} onClick={() => go("post")}><FileText size={14} /> {t("Post", "Posts")} {stats.drafts ? `(${stats.drafts})` : ""}</Button>
          <Button variant="ghost" onClick={() => go("isu")}>{t("Isu semasa", "Current issues")}</Button>
          <Button variant="ghost" onClick={() => setArranging(true)} data-arrange-dashboard><LayoutGrid size={14} /> {t("Susun papan", "Arrange")}</Button>
        </div>
      </motion.div>
    </AuroraBackground>
  );

  const aside = (shows("ai") || shows("subs")) ? (
    <div>
    {shows("ai") && <Card className={shows("subs") ? "mb-4" : ""} data-ai-team>
      <CardHeader>
        <CardTitle>{t("Pasukan AI", "AI team")}</CardTitle>
        <CardDescription>{settings?.ai_team_state?.reader?.chosen
          ? t("{r} menulis sekarang · {m}", "{r} writes now · {m}", { r: settings.ai_team_state.reader.chosen.name, m: settings.ai_team_state.reader.chosen.model })
          : t("Robot Wanshah; pengarah pilih yang terpantas.", "Wanshah's robots; the router picks the fastest.")}</CardDescription>
      </CardHeader>
      <CardContent>
        <AiTeam statusRows={apiT.rows} usageRows={usageT.rows} state={settings?.ai_team_state} team={settings?.ai_team} compact />
        <Button size="sm" variant="ghost" className="mt-3" onClick={() => go("api")}>{t("Tab API", "API tab")}</Button>
      </CardContent>
    </Card>}
    {shows("subs") && <Card data-subs-widget>
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
    </Card>}
    </div>
  ) : null;

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
        below={shows("charts") ? <HomeCharts className="grid gap-4 sm:grid-cols-2" ideas={ideas.rows} posts={posts.rows} log={log.rows} usage={usageT.rows} today={today} /> : null}
        show={{ chart: shows("chart"), projects: shows("queue"), activity: shows("activity") }}
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
      <Modal open={arranging} onClose={() => setArranging(false)} title={t("Susun papan", "Arrange the dashboard")}>
        <DashboardLayoutConfigurator className="max-w-none border-0 shadow-none" availableWidgets={widgetList} visibleWidgetIds={visible}
          onVisibilityChange={keepLayout} onLayoutReset={() => keepLayout(widgetList.map((x) => x.id))}
          words={{ title: t("Konfigurasi papan", "Dashboard configuration"), description: t("Pilih widget yang dipapar. Disimpan untuk setiap peranti.", "Choose which widgets show. Saved for every device."),
            visibility: t("Widget yang dipapar", "Widget visibility"), reset: t("Pulihkan susun atur asal", "Reset layout to default") }} />
      </Modal>
    </main>
  );
}

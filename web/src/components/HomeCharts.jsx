import { useMemo } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useLang } from "../lib/i18n";
import { ideaStatusCounts, postsByTopic, sentByChannel, tokensByDay } from "../lib/dashboard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/app-1-utils/card";

/* More graphs on Papan (Wan, 7 Nov 2026: "can add more graph in overview"): four small charts from rows the page already
   holds, worked out in lib/dashboard.js (tested in dashboard.test.mjs). Nothing here writes. */
const ACCENT = "rgb(var(--c-accent))";
const LINE = "rgb(var(--c-line))";
const MUTED = "#94a3b8";
const OK = "#10b981";
const BAD = "#ef4444";
const STATE_COLOUR = { new: ACCENT, working: "#6366f1", drafted: OK, error: BAD, rejected: MUTED };
const TOPIC_COLOURS = ["#d97706", "#2563eb", "#10b981", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#94a3b8"];
const STATE_WORDS = { new: ["Baharu", "New"], working: ["Ditulis", "Writing"], drafted: ["Jadi draf", "Drafted"], error: ["Gagal", "Failed"], rejected: ["Ditolak", "Rejected"] };
const TOPIC_WORDS = {
  kosmetik: ["Kosmetik", "Cosmetics"], kajian_kes: ["Kajian kes", "Case study"], sains_kosmetik: ["Sains kosmetik", "Cosmetic science"], halal_my: ["Halal", "Halal"],
  fatwa: ["Fatwa", "Fatwa"], farmaseutikal: ["Farmaseutikal", "Pharma"], makanan: ["Makanan", "Food"], linkedin: ["LinkedIn", "LinkedIn"], other: ["Lain", "Other"],
};
const fmtK = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
const tip = { contentStyle: { fontSize: 12, borderRadius: 10 }, cursor: { fill: "rgba(148,163,184,0.12)" } };

function Panel({ title, description, children, empty, isEmpty, id }) {
  return (
    <Card className="min-w-0" data-home-chart={id}>
      <CardHeader className="pb-2"><CardTitle className="text-base">{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader>
      <CardContent>{isEmpty ? <p className="grid h-[180px] place-items-center text-xs text-muted">{empty}</p> : <div className="h-[180px]">{children}</div>}</CardContent>
    </Card>
  );
}

export default function HomeCharts({ ideas, posts, log, usage, today, className = "mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4" }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const states = useMemo(() => ideaStatusCounts(ideas), [ideas]);
  const channels = useMemo(() => sentByChannel(log, today, 30), [log, today]);
  const tokens = useMemo(() => tokensByDay(usage, today, 14), [usage, today]);
  const topics = useMemo(() => postsByTopic(posts, today, 30), [posts, today]);
  const tokenTotal = tokens.reduce((n, d) => n + d.tokens, 0);
  const failed = tokens.reduce((n, d) => n + d.failed, 0);

  return (
    <section className={className} data-home-charts>
      <Panel id="ideas" title={t("Idea ikut status", "Ideas by status")} description={t("Di mana setiap idea berada sekarang", "Where every idea stands now")}
        isEmpty={!states.length} empty={t("Belum ada idea.", "No ideas yet.")}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={states.map((s) => ({ ...s, label: STATE_WORDS[s.status]?.[L] || s.status }))} layout="vertical" margin={{ left: 4, right: 12 }}>
            <CartesianGrid horizontal={false} stroke={LINE} />
            <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} stroke={MUTED} />
            <YAxis type="category" dataKey="label" width={70} tick={{ fontSize: 11 }} stroke={MUTED} />
            <Tooltip {...tip} formatter={(v) => [v, t("idea", "ideas")]} />
            <Bar dataKey="n" radius={[0, 6, 6, 0]}>{states.map((s) => <Cell key={s.status} fill={STATE_COLOUR[s.status] || MUTED} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel id="channels" title={t("Siaran ikut saluran", "Posts by channel")} description={t("30 hari: dihantar dan ralat penerbit", "30 days: sent and publisher errors")}
        isEmpty={!channels.length} empty={t("Tiada siaran dalam 30 hari.", "Nothing sent in 30 days.")}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={channels} margin={{ left: -18, right: 6 }}>
            <CartesianGrid vertical={false} stroke={LINE} />
            <XAxis dataKey="channel" tick={{ fontSize: 10 }} stroke={MUTED} />
            <YAxis allowDecimals={false} tick={{ fontSize: 10 }} stroke={MUTED} />
            <Tooltip {...tip} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="sent" name={t("Dihantar", "Sent")} stackId="a" fill={OK} />
            <Bar dataKey="error" name={t("Ralat", "Errors")} stackId="a" fill={BAD} radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel id="tokens" title={t("Token AI sehari", "AI tokens a day")}
        description={t("14 hari · {n} token · {f} panggilan gagal", "14 days · {n} tokens · {f} failed calls", { n: fmtK(tokenTotal), f: failed })}
        isEmpty={!tokenTotal} empty={t("Tiada penggunaan dalam 14 hari.", "No usage in 14 days.")}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={tokens} margin={{ left: -12, right: 6 }}>
            <defs><linearGradient id="home-tokens" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} /><stop offset="100%" stopColor={ACCENT} stopOpacity={0} /></linearGradient></defs>
            <CartesianGrid vertical={false} stroke={LINE} />
            <XAxis dataKey="date" tickFormatter={(d) => d.slice(8, 10)} tick={{ fontSize: 10 }} stroke={MUTED} interval={1} />
            <YAxis tickFormatter={fmtK} tick={{ fontSize: 10 }} stroke={MUTED} />
            <Tooltip {...tip} formatter={(v, k) => [k === "tokens" ? fmtK(v) : v, k === "tokens" ? t("token", "tokens") : k]} />
            <Area dataKey="tokens" type="monotone" stroke={ACCENT} fill="url(#home-tokens)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </Panel>

      <Panel id="topics" title={t("Post ikut topik", "Posts by topic")} description={t("30 hari: domain ws.regulab dan LinkedIn", "30 days: ws.regulab domains and LinkedIn")}
        isEmpty={!topics.length} empty={t("Tiada post dalam 30 hari.", "No posts in 30 days.")}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={topics.map((x) => ({ ...x, label: TOPIC_WORDS[x.topic]?.[L] || x.topic }))} dataKey="n" nameKey="label" innerRadius={42} outerRadius={70} paddingAngle={2}>
              {topics.map((x, i) => <Cell key={x.topic} fill={TOPIC_COLOURS[i % TOPIC_COLOURS.length]} />)}
            </Pie>
            <Tooltip {...tip} formatter={(v) => [v, t("post", "posts")]} />
            <Legend layout="vertical" align="right" verticalAlign="middle" wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      </Panel>
    </section>
  );
}

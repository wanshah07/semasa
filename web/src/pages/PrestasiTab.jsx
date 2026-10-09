import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BarChart3, CalendarClock, Eye, Flame, MessageCircle, Percent, Trophy, Users } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { stampMYT } from "../lib/format";
import { fmtDate } from "../lib/billing";
import { CHANNELS, DAYS, WINDOWS, bestWindow, byChannel, cellLabel, daily, filterRows, heatmap, interactionsOf, mytSlot, overview, ranked, viewsOf } from "../lib/analytics";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Segmented } from "../components/ui/Field";

/* Prestasi: what each post did, the way Threads' own analytics screen shows it (Wan, 9 Oct 2026, two screenshots): account
   reach/views, average views a post, engagement, replies, the peak post, the best publishing window, a day × 3-hour heatmap
   of posting performance and a window inspector. Rows come from semasa_post_metrics (supabase/034_post_metrics.sql), which
   backend/semasa/metrics.py fills from Buffer once a day; lib/analytics.js does the arithmetic in Malaysia time. The page
   writes nothing. LinkedIn has no figures (the connection cannot read them), and the page says so. */

const today = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
const CHANNEL_WORDS = { threads: "Threads", instagram: "Instagram", facebook: "Facebook" };
const DAY_WORDS = { bm: ["Ahd", "Isn", "Sel", "Rab", "Kha", "Jum", "Sab"], en: DAYS };
const fmt = (n) => (n >= 10000 ? `${(n / 1000).toFixed(1)}k` : String(Math.round(n || 0)));

export default function PrestasiTab({ posts, go }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? "en" : "bm";
  const metricsT = useTable(TABLES.postMetrics, { enabled: true, order: "sent_at", limit: 3000, realtime: false, everyMs: 300_000 });
  const [channel, setChannel] = useState("");
  const [days, setDays] = useState(30);
  const [picked, setPicked] = useState(null);                       // the heatmap cell under inspection: {dow, win}
  const day = today();
  const rows = useMemo(() => filterRows(metricsT.rows, { channel, days, today: day }), [metricsT.rows, channel, days, day]);
  const o = useMemo(() => overview(rows), [rows]);
  const cells = useMemo(() => heatmap(rows), [rows]);
  const best = useMemo(() => bestWindow(cells, 1), [cells]);
  const series = useMemo(() => daily(rows, day, days), [rows, day, days]);
  const split = useMemo(() => byChannel(rows), [rows]);
  const top = useMemo(() => ranked(rows).slice(0, 40), [rows]);
  const postsById = useMemo(() => Object.fromEntries((posts?.rows || []).map((p) => [p.id, p])), [posts]);
  const inspect = picked ? cells[picked.dow * 8 + picked.win] : best;
  const missing = /semasa_post_metrics/.test(metricsT.error || "");
  const lastRead = metricsT.rows.reduce((m, r) => (r.fetched_at > m ? r.fetched_at : m), "");
  const dayWords = DAY_WORDS[L];
  const reachKnown = channel === "instagram";
  const nameOf = (r) => (r.post_id && postsById[r.post_id]?.hook) || r.text_head || "";

  const tiles = [
    { label: reachKnown ? t("Jangkauan", "Reach") : t("Tontonan akaun", "Account views"), value: fmt(reachKnown ? o.reach : o.views), icon: reachKnown ? Users : Eye,
      hint: t("{n} post dalam {d} hari", "{n} posts in {d} days", { n: o.posts, d: days }) },
    { label: t("Purata tontonan", "Avg views"), value: fmt(o.avgViews), icon: BarChart3, hint: t("setiap post", "per post") },
    { label: t("Penglibatan", "Engagement"), value: `${o.engagement}%`, icon: Percent, hint: t("interaksi ÷ tontonan", "interactions ÷ views") },
    { label: t("Balasan", "Replies"), value: fmt(o.replies), icon: MessageCircle, hint: t("komen di semua saluran", "comments across channels") },
  ];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div {...fadeUp} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Prestasi", "Performance")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Apa yang setiap post buat di saluran: tontonan, penglibatan, balasan, post terbaik dan tetingkap siaran terbaik, dalam waktu Malaysia. Angka dibaca dari Buffer sekali sehari.",
            "What every post did on its channel: views, engagement, replies, the peak post and the best publishing window, in Malaysia time. Figures are read from Buffer once a day.")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented value={channel} onChange={(v) => { setChannel(v); setPicked(null); }}
            options={[["", t("Semua", "All")], ...CHANNELS.map((c) => [c, CHANNEL_WORDS[c]])]} />
          <Segmented value={String(days)} onChange={(v) => { setDays(Number(v)); setPicked(null); }}
            options={[["7", t("7 hari", "7 days")], ["30", t("30 hari", "30 days")], ["90", t("90 hari", "90 days")]]} />
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/034_post_metrics.sql sekali, kemudian larian Metrics di GitHub.", "The table is not there yet: run supabase/034_post_metrics.sql once, then the Metrics workflow on GitHub.")}</p>}
      {metricsT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{metricsT.error}</p>}
      {!metricsT.loading && !metricsT.error && !metricsT.rows.length && (
        <p className="mb-4 rounded-tile bg-surface-2 p-3 text-sm text-muted">{t("Tiada angka lagi: larian Metrics (GitHub → Actions → Metrics → Run workflow) membaca Buffer dan mengisi jadual ini.",
          "No figures yet: the Metrics workflow (GitHub → Actions → Metrics → Run workflow) reads Buffer and fills this table.")}</p>
      )}

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((s) => (
          <Card key={s.label} className="p-4">
            <div className="flex items-center justify-between"><span className="text-[11px] uppercase tracking-widest text-muted">{s.label}</span><s.icon size={16} className="text-muted" /></div>
            <p className="mt-2 font-display text-2xl tabular-nums">{s.value}</p>
            <p className="mt-0.5 text-xs text-muted">{s.hint}</p>
          </Card>
        ))}
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-medium">{t("Tontonan sehari", "Views a day")}</h2>
            <span className="text-[11px] text-muted">{t("{d} hari terakhir, waktu Malaysia", "last {d} days, Malaysia time", { d: days })}</span>
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={series} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
                <defs><linearGradient id="prestasi-views" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="rgb(var(--c-accent))" stopOpacity={0.35} /><stop offset="95%" stopColor="rgb(var(--c-accent))" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid vertical={false} stroke="rgb(var(--c-line))" />
                <XAxis dataKey="date" tickFormatter={(d) => d.slice(8, 10)} tick={{ fontSize: 10 }} stroke="rgb(var(--c-muted))" interval={days > 30 ? 9 : days > 7 ? 4 : 0} />
                <YAxis tick={{ fontSize: 10 }} stroke="rgb(var(--c-muted))" allowDecimals={false} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12 }} labelFormatter={(d) => fmtDate(d)}
                  formatter={(v, k) => [v, k === "views" ? t("Tontonan", "Views") : k === "posts" ? t("Post", "Posts") : t("Balasan", "Replies")]} />
                <Area dataKey="views" type="monotone" stroke="rgb(var(--c-accent))" fill="url(#prestasi-views)" strokeWidth={2} />
                <Area dataKey="posts" type="monotone" stroke="rgb(var(--c-muted))" fill="none" strokeWidth={1} strokeDasharray="4 4" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card className="p-4">
          <h2 className="flex items-center gap-2 text-sm font-medium"><Trophy size={14} className="text-gold" /> {t("Post puncak", "Peak post")}</h2>
          {o.peak ? (
            <div className="mt-2">
              <p className="line-clamp-4 text-sm">{nameOf(o.peak)}</p>
              <p className="mt-2 text-xs text-muted">{CHANNEL_WORDS[o.peak.channel] || o.peak.channel} · {stampMYT(o.peak.sent_at)}</p>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <Stat label={t("Tontonan", "Views")} value={fmt(viewsOf(o.peak))} />
                <Stat label={t("Interaksi", "Interactions")} value={fmt(interactionsOf(o.peak))} />
                <Stat label={t("Balasan", "Replies")} value={fmt(o.peak.comments || 0)} />
              </div>
              <div className="mt-3 flex gap-2">
                {o.peak.url && <a className="text-xs text-accent underline" href={o.peak.url} target="_blank" rel="noreferrer">{t("Buka post", "Open post")}</a>}
                {o.peak.post_id && go && <button type="button" className="text-xs text-accent underline" onClick={() => go("post", o.peak.post_id)}>{t("Lihat dalam Post", "See in Posts")}</button>}
              </div>
            </div>
          ) : <p className="mt-2 text-sm text-muted">{t("Tiada post dalam julat ini.", "No post in this range.")}</p>}
        </Card>
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-medium"><Flame size={14} className="text-accent" /> {t("Prestasi siaran mengikut masa", "Posting performance by time")}</h2>
              <p className="text-[11px] text-muted">{t("Purata tontonan setiap post, hari × tetingkap 3 jam (MYT). Warna lebih pekat = purata lebih tinggi; angka = bilangan post. Klik satu sel.",
                "Average views a post, day × 3-hour window (MYT). Deeper colour = higher average; the number = posts. Click a cell.")}</p>
            </div>
            {best && <span className="rounded-pill bg-accent/15 px-2 py-0.5 text-[11px] text-accent">{t("Terbaik", "Best")}: {cellLabel(best)} · {fmt(best.avgViews)} {t("purata", "avg")}</span>}
          </div>
          <div className="overflow-x-auto">
            <div className="grid min-w-[520px] gap-1" style={{ gridTemplateColumns: "44px repeat(8, minmax(0, 1fr))" }}>
              <div />
              {WINDOWS.map((w) => <div key={w} className="text-center text-[10px] text-muted">{w}</div>)}
              {Array.from({ length: 7 }, (_, dow) => (
                <RowCells key={dow} dow={dow} cells={cells} picked={picked} best={best} setPicked={setPicked} label={dayWords[dow]} />
              ))}
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <h2 className="flex items-center gap-2 text-sm font-medium"><CalendarClock size={14} className="text-accent" /> {t("Pemeriksa tetingkap", "Window inspector")}</h2>
          {inspect ? (
            <div className="mt-2">
              <p className="font-display text-xl">{cellLabel(inspect)}</p>
              <p className="text-xs text-muted">{picked ? t("sel yang dipilih", "the cell you picked") : t("tetingkap siaran terbaik", "the best publishing window")}</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Stat label={t("Purata tontonan", "Average views")} value={fmt(inspect.avgViews)} />
                <Stat label={t("Jumlah tontonan", "Total views")} value={fmt(inspect.views)} />
                <Stat label={t("Balasan", "Replies")} value={fmt(inspect.replies)} />
                <Stat label={t("Penglibatan", "Engagement")} value={`${inspect.engagement}%`} />
              </div>
              <p className="mt-3 text-[11px] uppercase tracking-widest text-muted">{t("{n} post", "{n} posts", { n: inspect.posts })}</p>
              <ol className="mt-1 flex flex-col gap-1">
                {ranked(inspect.rows).slice(0, 6).map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className="truncate">{CHANNEL_WORDS[r.channel] || r.channel} · {nameOf(r)}</span>
                    <span className="shrink-0 font-mono tabular-nums">{fmt(viewsOf(r))}</span>
                  </li>
                ))}
              </ol>
              {picked && <Button size="sm" variant="ghost" className="mt-3" onClick={() => setPicked(null)}>{t("Kembali ke yang terbaik", "Back to the best")}</Button>}
            </div>
          ) : <p className="mt-2 text-sm text-muted">{t("Tiada post dalam julat ini.", "No post in this range.")}</p>}
        </Card>
      </div>

      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        {split.map((c) => (
          <Card key={c.channel} className="p-4">
            <div className="flex items-center justify-between"><span className="text-sm font-medium">{CHANNEL_WORDS[c.channel]}</span><span className="text-[11px] text-muted">{t("{n} post", "{n} posts", { n: c.posts })}</span></div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              <Stat label={c.channel === "facebook" ? t("Paparan", "Impressions") : t("Tontonan", "Views")} value={fmt(c.views)} />
              <Stat label={t("Purata", "Avg")} value={fmt(c.avgViews)} />
              <Stat label={t("Penglibatan", "Engagement")} value={`${c.engagement}%`} />
            </div>
          </Card>
        ))}
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] uppercase tracking-widest text-muted">
            <tr>
              <th className="px-4 py-3">{t("Post", "Post")}</th>
              <th className="px-3 py-3">{t("Saluran", "Channel")}</th>
              <th className="px-3 py-3">{t("Disiar (MYT)", "Sent (MYT)")}</th>
              <th className="px-3 py-3 text-right">{t("Tontonan", "Views")}</th>
              <th className="px-3 py-3 text-right">{t("Reaksi", "Reactions")}</th>
              <th className="px-3 py-3 text-right">{t("Balasan", "Replies")}</th>
              <th className="px-3 py-3 text-right">{t("Kongsi", "Shares")}</th>
              <th className="px-3 py-3 text-right">{t("Penglibatan", "Eng.")}</th>
            </tr>
          </thead>
          <tbody>
            {top.map((r) => {
              const s = mytSlot(r.sent_at);
              return (
                <tr key={r.id} className="border-t border-line/70 align-top">
                  <td className="max-w-md px-4 py-3">
                    <div className="line-clamp-2">{nameOf(r)}</div>
                    <div className="mt-0.5 flex gap-2 text-xs">
                      {r.url && <a className="text-accent underline" href={r.url} target="_blank" rel="noreferrer">{t("Buka", "Open")}</a>}
                      {r.post_id && go && <button type="button" className="text-accent underline" onClick={() => go("post", r.post_id)}>{t("Post", "Post")}</button>}
                    </div>
                  </td>
                  <td className="px-3 py-3">{CHANNEL_WORDS[r.channel] || r.channel}</td>
                  <td className="px-3 py-3 text-xs tabular-nums">{stampMYT(r.sent_at)}{s ? <div className="text-muted">{dayWords[s.dow]} · {WINDOWS[s.win]}</div> : null}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{fmt(viewsOf(r))}{r.reach != null && <div className="text-xs text-muted">{t("jangkauan", "reach")} {r.reach}</div>}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.reactions ?? "—"}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.comments ?? "—"}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{(r.shares ?? 0) + (r.reposts ?? 0) || "—"}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{r.engagement != null ? `${r.engagement}%` : "—"}</td>
                </tr>
              );
            })}
            {!top.length && !metricsT.loading && <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-muted">{t("Tiada post dalam julat ini.", "No post in this range.")}</td></tr>}
          </tbody>
        </table>
      </Card>

      <p className="mt-4 text-[11px] text-muted">
        {t("Sumber: Buffer (Facebook paparan, Instagram tontonan + jangkauan, Threads tontonan). LinkedIn tiada angka: sambungan hanya boleh menyiar, bukan membaca. Bacaan terakhir: {at}.",
          "Source: Buffer (Facebook impressions, Instagram views + reach, Threads views). LinkedIn has no figures: the connection can post but not read. Last read: {at}.",
          { at: lastRead ? stampMYT(lastRead) : "—" })}
      </p>
    </main>
  );
}

function RowCells({ dow, cells, picked, best, setPicked, label }) {
  return (
    <>
      <div className="flex items-center text-[11px] text-muted">{label}</div>
      {Array.from({ length: 8 }, (_, win) => {
        const c = cells[dow * 8 + win];
        const isPicked = picked && picked.dow === dow && picked.win === win;
        const isBest = !picked && best && best.dow === dow && best.win === win;
        return (
          <button type="button" key={win} onClick={() => setPicked({ dow, win })} title={`${cellLabel(c)}: ${c.posts} posts, avg ${c.avgViews}`}
            className={`flex h-9 items-center justify-center rounded-md text-[11px] tabular-nums transition ${isPicked || isBest ? "ring-2 ring-accent" : ""} ${c.posts ? "text-ink" : "text-muted/60"}`}
            style={{ background: c.posts ? `rgb(var(--c-accent) / ${0.12 + 0.75 * c.heat})` : "rgb(var(--c-surface-2))" }}>
            {c.posts || ""}
          </button>
        );
      })}
    </>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded-tile bg-surface-2/60 p-2">
      <p className="text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className="font-display text-lg tabular-nums">{value}</p>
    </div>
  );
}

"use client";
/* App-1 (pasted by Wan on 9 Oct 2026, a 21st.dev dashboard). In Semasa it is the Bil overview: four stat tiles, one chart of money
   invoiced against money paid by week, the open projects with how far each is paid, and the latest activity. Three things changed
   from the paste, each because of what this repo is:
     - no sidebar and no header: Semasa has its own (components/AppSidebar.jsx), and a second one inside a tab is a second navigation;
       the SidebarProvider / App1Sidebar / app-1-data files were never pasted and are not needed;
     - everything is a PROP: the paste carried its own invented numbers, and a dashboard that shows invented numbers is worse than none
       (pages/BillingTab.jsx computes them from the live documents with lib/billing.js);
     - the chart colours are tokens validated for both themes (accent and gold; the gold steps darker under noir), the two series
       separate by form as well (dashed line against a filled area), a legend is always drawn, and the documents table under the
       overview is the table view the dataviz method asks for. */
import * as React from "react";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import type { LucideIcon } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/table-2-utils/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/app-1-utils/card";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

export type OverviewStat = { label: string; value: string; hint?: string; icon: LucideIcon; tone?: "" | "ok" | "danger" };
export type OverviewPoint = { week: string } & Record<string, number | string>;
/** Which two fields of a point the chart draws: `line` is the dashed line, `area` the filled area (the Bil tab's
    invoiced/paid; the home dashboard's drafted/published). Each names its label in `words`. */
export type OverviewKeys = { line: string; area: string };
export type OverviewProject = {
  id: string; name: string; description?: string; progress: number; status: string;
  badge?: "default" | "secondary" | "destructive" | "outline"; due?: string; team: { name: string; initials: string }[];
  onClick?: () => void;
};
export type OverviewActivity = { id: string; person: { name: string; initials: string }; action: string; time: string; onClick?: () => void };

export type OverviewWords = {
  chartTitle: string; chartDescription: string; invoiced: string; paid: string;   // the labels of `keys.line` and `keys.area`
  projectsTitle: string; projectsDescription: string; noProjects: string; due: string;
  activityTitle: string; activityDescription: string; noActivity: string;
};

type Props = {
  stats: OverviewStat[];
  series: OverviewPoint[];
  projects: OverviewProject[];
  activity: OverviewActivity[];
  words: OverviewWords;
  /** Drawn beside the chart (the Bil tab puts the aging bar here). */
  aside?: React.ReactNode;
  /** The tooltip's number format (money). */
  formatValue?: (n: number) => string;
  /** The point fields to draw; default invoiced (line) and paid (area). */
  keys?: OverviewKeys;
  /** Drawn above the stat tiles (the home dashboard's hero band). */
  header?: React.ReactNode;
  className?: string;
};

export function App1({ stats, series, projects, activity, words, aside, formatValue, keys, header, className }: Props) {
  const k: OverviewKeys = keys || { line: "invoiced", area: "paid" };
  const config: ChartConfig = {
    [k.line]: { label: words.invoiced, theme: { light: "#C9A24B", dark: "#B38B2D" } },   // --c-gold; darker step under noir
    [k.area]: { label: words.paid, theme: { light: "#3FA6EE", dark: "#4898D8" } },       // --c-accent in each theme
  };
  const fmt = formatValue || ((n: number) => n.toLocaleString());
  const gradId = `app1fill-${React.useId().replace(/[^a-zA-Z0-9]/g, "")}`;     // two dashboards on one page must not share a <defs> id
  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {header}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.label} className={cn(stat.tone === "danger" && "border-danger/40", stat.tone === "ok" && "border-ok/40")}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-[11px] font-normal uppercase tracking-widest text-muted">{stat.label}</CardTitle>
              <stat.icon aria-hidden className="size-4 text-muted" />
            </CardHeader>
            <CardContent>
              <p className={cn("font-display text-2xl tabular-nums", stat.tone === "danger" ? "text-danger" : "text-ink")}>{stat.value}</p>
              {stat.hint && <p className="mt-0.5 text-xs text-muted">{stat.hint}</p>}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className={cn("grid gap-4", aside && "lg:grid-cols-[3fr_2fr]")}>
        <Card>
          <CardHeader>
            <CardTitle>{words.chartTitle}</CardTitle>
            <CardDescription>{words.chartDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={config} className="h-56 w-full">
              <AreaChart data={series} margin={{ left: 4, right: 4, top: 8 }} accessibilityLayer>
                <defs>
                  <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={`var(--color-${k.area})`} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={`var(--color-${k.area})`} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="week" tickLine={false} axisLine={false} tickMargin={8} />
                <YAxis tickLine={false} axisLine={false} width={44} tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v))} />
                <ChartTooltip content={<ChartTooltipContent formatter={(v, name) => (
                  <div className="flex flex-1 items-center justify-between gap-3">
                    <span className="text-muted">{config[String(name)]?.label || String(name)}</span>
                    <span className="font-mono tabular-nums text-ink">{fmt(Number(v))}</span>
                  </div>
                )} />} />
                <ChartLegend content={<ChartLegendContent />} />
                {/* identity by form as well as colour: invoiced is a dashed line, paid a filled area */}
                <Area dataKey={k.line} type="monotone" stroke={`var(--color-${k.line})`} strokeDasharray="4 4" fill="none" strokeWidth={2} />
                <Area dataKey={k.area} type="monotone" stroke={`var(--color-${k.area})`} fill={`url(#${gradId})`} strokeWidth={2} />
              </AreaChart>
            </ChartContainer>
          </CardContent>
        </Card>
        {aside}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{words.projectsTitle}</CardTitle>
            <CardDescription>{words.projectsDescription}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {projects.map((p) => (
              <div key={p.id} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between gap-2">
                  {p.onClick ? (
                    <button type="button" onClick={p.onClick} className="truncate text-left text-sm font-medium hover:underline">{p.name}</button>
                  ) : <h3 className="truncate text-sm font-medium">{p.name}</h3>}
                  <Badge variant={p.badge || "outline"} className="shrink-0 text-[10px]">{p.status}</Badge>
                </div>
                {p.description && <p className="text-xs text-muted">{p.description}</p>}
                <div className="flex items-center gap-3">
                  <Progress value={p.progress} aria-label={`${p.name} ${p.progress}%`} />
                  <span className="shrink-0 text-xs tabular-nums text-muted">{p.progress}%</span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1">
                    {p.team.map((m) => (
                      <Avatar key={m.name} size="sm" className="border border-line bg-surface-2" title={m.name}>
                        <AvatarFallback className="text-[9px]">{m.initials}</AvatarFallback>
                      </Avatar>
                    ))}
                  </span>
                  {p.due && <span className="text-xs text-muted">{words.due} {p.due}</span>}
                </div>
              </div>
            ))}
            {!projects.length && <p className="text-xs text-muted">{words.noProjects}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{words.activityTitle}</CardTitle>
            <CardDescription>{words.activityDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="flex max-h-72 flex-col gap-3 overflow-y-auto">
              {activity.map((e) => (
                <li key={e.id} className="flex items-start gap-3">
                  <Avatar size="sm" className="mt-0.5 border border-line bg-surface-2">
                    <AvatarFallback className="text-[9px]">{e.person.initials}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm leading-snug">
                      {e.onClick ? <button type="button" onClick={e.onClick} className="font-medium hover:underline">{e.person.name}</button> : <span className="font-medium">{e.person.name}</span>}{" "}
                      <span className="text-muted">{e.action}</span>
                    </p>
                    <p className="text-xs text-muted">{e.time}</p>
                  </div>
                </li>
              ))}
              {!activity.length && <li className="text-xs text-muted">{words.noActivity}</li>}
            </ol>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default App1;

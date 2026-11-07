// This is file of your component
// You can use any dependencies from npm; we import them automatically in package.json

/* Pasted by Wan, 7 Nov 2026 ("Apply this if relevant"), kept as pasted. Semasa uses its pieces — GlowCard, CardTitle,
   LiveBadge, Icon, the TECHS marks and useAnimatedNumber, exported below — in the Technology overview
   (pages/TechOverviewTab.jsx), fed with REAL figures from semasa_api_status and semasa_repos. The default export,
   TechStackBento, is the original demo: its "live" numbers are Math.random and it is never rendered in the app. */

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, MouseEvent, ReactNode, TouchEvent } from "react";

/* ==========================================================================
   Types
   ========================================================================== */

export type Accent = "indigo" | "cyan" | "emerald" | "fuchsia" | "amber";
type LineType = "cmd" | "ok" | "info" | "url";

export interface Tech {
  id: string;
  name: string;
  version: string;
  desc: string;
  rgb: string; // "r, g, b" so we can use it inside rgba()
  icon: ReactNode;
}

interface TermLine {
  type: LineType;
  text: string;
}

// end of types


/* ==========================================================================
   Constants
   ========================================================================== */

// Spotlight colors, as "r, g, b"
export const ACCENTS: Record<Accent, string> = {
  indigo: "129, 140, 248",
  cyan: "34, 211, 238",
  emerald: "52, 211, 153",
  fuchsia: "232, 121, 249",
  amber: "251, 191, 36",
};

// Faint grid that only shows near the cursor
const GRID_IMAGE =
  "linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)";

const SERIES_LENGTH = 40; // points in the latency chart
const TICK_MS = 1200; // how often the live data updates

const REGIONS = [
  { name: "US East", base: 24 },
  { name: "EU West", base: 48 },
  { name: "São Paulo", base: 71 },
  { name: "Singapore", base: 94 },
];

const SCRIPT: TermLine[] = [
  { type: "cmd", text: "pnpm install" },
  { type: "ok", text: "312 packages installed in 2.1s" },
  { type: "cmd", text: "pnpm build" },
  { type: "info", text: "Compiling routes and components…" },
  { type: "ok", text: "Compiled successfully in 4.2s" },
  { type: "ok", text: "Type check passed, 0 errors" },
  { type: "ok", text: "24 static pages generated" },
  { type: "cmd", text: "deploy --prod" },
  { type: "info", text: "Uploading 18 files…" },
  { type: "ok", text: "Deployed to production" },
  { type: "url", text: "https://app.example.dev" },
];

const TERM_VISIBLE = 11; // lines shown at once
const LINE_STYLES: Record<LineType, { mark: string; markClass: string; textClass: string }> = {
  cmd: { mark: "$", markClass: "text-fuchsia-300", textClass: "text-slate-100" },
  ok: { mark: "✓", markClass: "text-emerald-300", textClass: "text-slate-300" },
  info: { mark: "›", markClass: "text-slate-500", textClass: "text-slate-400" },
  url: { mark: "●", markClass: "text-cyan-300", textClass: "text-cyan-300 underline underline-offset-2" },
};

const LIGHTHOUSE = [
  { label: "Perf", score: 98 },
  { label: "A11y", score: 100 },
  { label: "Best", score: 96 },
  { label: "SEO", score: 100 },
];

// end of constants


/* ==========================================================================
   Helpers
   ========================================================================== */

// Join class names, skipping anything falsy
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

const clamp = (n: number, min: number, max: number) => Math.min(Math.max(n, min), max);

// Counts smoothly from the current number to a new one whenever the target changes
export function useAnimatedNumber(target: number, duration = 700): number {
  const [value, setValue] = useState(target);
  const current = useRef(target);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      current.current = target;
      setValue(target);
      return;
    }

    const from = current.current;
    const start = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      current.current = from + (target - from) * eased;
      setValue(current.current);
      if (t < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration]);

  return value;
}

// A first batch of believable latency numbers (same every time, so the page is stable on load)
function initialSeries(): number[] {
  return Array.from({ length: SERIES_LENGTH }, (_, i) => 40 + Math.sin(i * 0.5) * 9 + ((i * 37) % 7));
}

// Smooth line through chart points
function toSmoothPath(points: Array<{ x: number; y: number }>): string {
  return points.reduce((d, p, i) => {
    if (i === 0) return `M ${p.x} ${p.y}`;
    const prev = points[i - 1];
    const mid = (prev.x + p.x) / 2;
    return `${d} C ${mid} ${prev.y}, ${mid} ${p.y}, ${p.x} ${p.y}`;
  }, "");
}

const statusOf = (ms: number) =>
  ms < 60
    ? { dot: "bg-emerald-400", text: "text-emerald-300" }
    : ms < 100
    ? { dot: "bg-amber-400", text: "text-amber-300" }
    : { dot: "bg-rose-400", text: "text-rose-300" };

// end of helpers


/* ==========================================================================
   Inline SVG: framework and tool icons (simple original marks)
   ========================================================================== */

export function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="30"
      height="30"
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const TECHS: Tech[] = [
  {
    id: "react",
    name: "React",
    version: "19",
    desc: "React 19 · Component-driven user interfaces",
    rgb: "97, 218, 251",
    icon: (
      <Icon>
        <ellipse cx="16" cy="16" rx="12" ry="4.6" />
        <ellipse cx="16" cy="16" rx="12" ry="4.6" transform="rotate(60 16 16)" />
        <ellipse cx="16" cy="16" rx="12" ry="4.6" transform="rotate(120 16 16)" />
        <circle cx="16" cy="16" r="1.8" fill="currentColor" />
      </Icon>
    ),
  },
  {
    id: "next",
    name: "Next.js",
    version: "15",
    desc: "Next.js 15 · Routing, rendering and server actions",
    rgb: "226, 232, 240",
    icon: (
      <Icon>
        <circle cx="16" cy="16" r="12" />
        <path d="M12 21V11l9 11" />
        <path d="M20.5 11v6" />
      </Icon>
    ),
  },
  {
    id: "ts",
    name: "TypeScript",
    version: "5.6",
    desc: "TypeScript 5.6 · Typed code from the database to the UI",
    rgb: "96, 165, 250",
    icon: (
      <Icon>
        <rect x="4" y="4" width="24" height="24" rx="5" />
        <path d="M10 13h8M14 13v10" />
        <path d="M24 14.5c-.8-1-2-1.3-3-1-1.7.5-1.6 2.5.2 3.1l1.6.6c1.8.7 1.6 2.9-.2 3.3-1.2.3-2.4-.1-3.2-1.2" />
      </Icon>
    ),
  },
  {
    id: "tailwind",
    name: "Tailwind",
    version: "3.4",
    desc: "Tailwind 3.4 · Utility-first styling and design tokens",
    rgb: "56, 189, 248",
    icon: (
      <Icon>
        <path d="M5 11c2-4 5-6 9-5 2.2.6 3.2 2.2 5 3.5 2 1.4 4.3 1.5 8-.5-2 4-5 6-9 5-2.2-.6-3.2-2.2-5-3.5-2-1.4-4.3-1.5-8 .5Z" />
        <path d="M5 20c2-4 5-6 9-5 2.2.6 3.2 2.2 5 3.5 2 1.4 4.3 1.5 8-.5-2 4-5 6-9 5-2.2-.6-3.2-2.2-5-3.5-2-1.4-4.3-1.5-8 .5Z" />
      </Icon>
    ),
  },
  {
    id: "node",
    name: "Node.js",
    version: "22",
    desc: "Node.js 22 · API routes, workers and background jobs",
    rgb: "74, 222, 128",
    icon: (
      <Icon>
        <path d="m16 3 11 6.5v13L16 29 5 22.5v-13Z" />
        <circle cx="16" cy="16" r="3.4" />
      </Icon>
    ),
  },
  {
    id: "postgres",
    name: "Postgres",
    version: "16",
    desc: "PostgreSQL 16 · Primary database with row-level security",
    rgb: "129, 140, 248",
    icon: (
      <Icon>
        <ellipse cx="16" cy="8" rx="10" ry="4" />
        <path d="M6 8v8c0 2.2 4.5 4 10 4s10-1.8 10-4V8" />
        <path d="M6 16v8c0 2.2 4.5 4 10 4s10-1.8 10-4v-8" />
      </Icon>
    ),
  },
  {
    id: "redis",
    name: "Redis",
    version: "7",
    desc: "Redis 7 · Caching, rate limits and queues",
    rgb: "248, 113, 113",
    icon: (
      <Icon>
        <path d="m16 5 11 5-11 5-11-5Z" />
        <path d="m5 15 11 5 11-5" />
        <path d="m5 20 11 5 11-5" />
      </Icon>
    ),
  },
  {
    id: "docker",
    name: "Docker",
    version: "27",
    desc: "Docker 27 · Identical builds from laptop to production",
    rgb: "59, 130, 246",
    icon: (
      <Icon>
        <rect x="5" y="12" width="5" height="5" rx="1" />
        <rect x="11.5" y="12" width="5" height="5" rx="1" />
        <rect x="18" y="12" width="5" height="5" rx="1" />
        <rect x="11.5" y="6" width="5" height="5" rx="1" />
        <path d="M3 19h23.5c1.2-3 3-3.5 3-3.5-.4 5-4.5 10-13 10C8 25.5 3 22.5 3 19Z" />
      </Icon>
    ),
  },
];

// end of icons


/* ==========================================================================
   GlowCard: the shell every box uses.
   The cursor position lives in React state, and the border glow, the inner
   spotlight and the little grid all follow it.
   ========================================================================== */

export function GlowCard({
  accent,
  className = "",
  children,
}: {
  accent: Accent;
  className?: string;
  children: ReactNode;
}) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [active, setActive] = useState(false);
  const rgb = ACCENTS[accent];

  // Cursor position, measured from the card's top-left corner
  const moveTo = (clientX: number, clientY: number, el: HTMLElement) => {
    const rect = el.getBoundingClientRect();
    setPos({ x: clientX - rect.left, y: clientY - rect.top });
  };

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => moveTo(e.clientX, e.clientY, e.currentTarget);

  // Touch screens have no hover, so a finger dragging across the card lights it up too
  const handleTouch = (e: TouchEvent<HTMLDivElement>) => {
    const touch = e.touches[0];
    if (touch) {
      moveTo(touch.clientX, touch.clientY, e.currentTarget);
      setActive(true);
    }
  };

  const gridMask = `radial-gradient(220px circle at ${pos.x}px ${pos.y}px, black, transparent 75%)`;

  return (
    <div
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      onTouchStart={handleTouch}
      onTouchMove={handleTouch}
      onTouchEnd={() => setActive(false)}
      onFocus={() => setActive(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setActive(false);
      }}
      className={cx("relative rounded-3xl", className)}
    >
      {/* Edge layer 1: dim border */}
      <div aria-hidden="true" className="absolute inset-0 rounded-3xl bg-white/10" />

      {/* Edge layer 2: bright border that follows the cursor */}
      <div
        aria-hidden="true"
        className={cx("absolute inset-0 rounded-3xl transition-opacity duration-500", active ? "opacity-100" : "opacity-0")}
        style={{
          background: `radial-gradient(240px circle at ${pos.x}px ${pos.y}px, rgba(${rgb}, 0.95), transparent 70%)`,
        }}
      />

      {/* Card face: spotlight and grid live inside it */}
      <div aria-hidden="true" className="absolute inset-px overflow-hidden rounded-[23px] bg-[#0b0d15]">
        <div
          className={cx("absolute inset-0 transition-opacity duration-500", active ? "opacity-100" : "opacity-0")}
          style={{
            background: `radial-gradient(380px circle at ${pos.x}px ${pos.y}px, rgba(${rgb}, 0.14), transparent 65%)`,
          }}
        />
        <div
          className={cx("absolute inset-0 transition-opacity duration-500", active ? "opacity-100" : "opacity-0")}
          style={{
            backgroundImage: GRID_IMAGE,
            backgroundSize: "26px 26px",
            maskImage: gridMask,
            WebkitMaskImage: gridMask,
          }}
        />
      </div>

      {/* Content */}
      <div className="relative z-10 flex h-full flex-col p-5 sm:p-6">{children}</div>
    </div>
  );
}

// Title row shared by most cards
export function CardTitle({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h3 className="text-sm font-medium text-slate-300">{children}</h3>
      {right}
    </div>
  );
}

export function LiveBadge({ label = "Live" }: { label?: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-emerald-300">
      <span className="tb-pulse h-1.5 w-1.5 rounded-full bg-emerald-400" />
      {label}
    </span>
  );
}

// end of GlowCard


/* ==========================================================================
   Card 1: Server latency (large)
   ========================================================================== */

function LatencyCard() {
  const [series, setSeries] = useState<number[]>(initialSeries);
  const [pings, setPings] = useState<number[]>(() => REGIONS.map((r) => r.base));
  const [hover, setHover] = useState<number | null>(null);

  // A new reading every tick: the chart shifts left and the region numbers wobble a little
  useEffect(() => {
    const id = window.setInterval(() => {
      setSeries((prev) => [...prev.slice(1), clamp(prev[prev.length - 1] + (Math.random() - 0.5) * 16, 22, 88)]);
      setPings(REGIONS.map((r) => Math.round(clamp(r.base + (Math.random() - 0.5) * 14, 8, 140))));
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  const latest = Math.round(series[series.length - 1]);
  const average = Math.round(series.reduce((a, b) => a + b, 0) / series.length);
  const peak = Math.round(Math.max(...series));
  const animatedLatest = useAnimatedNumber(latest, 500);

  // Chart points on a 0 to 100 grid (the vertical scale is fixed at 0 to 100 ms)
  const points = series.map((v, i) => ({
    x: (i / (series.length - 1)) * 100,
    y: 95 - (v / 100) * 85,
  }));
  const line = toSmoothPath(points);
  const area = `${line} L 100 100 L 0 100 Z`;
  const shown = hover ?? series.length - 1;

  const handleChartMove = (e: MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = clamp((e.clientX - rect.left) / rect.width, 0, 1);
    setHover(Math.round(ratio * (series.length - 1)));
  };

  return (
    <GlowCard accent="indigo" className="min-h-[420px] sm:col-span-2 lg:row-span-2">
      <CardTitle right={<LiveBadge />}>Server latency</CardTitle>

      {/* Headline numbers */}
      <div className="mb-3 flex flex-wrap items-end gap-x-5 gap-y-2">
        <div className="flex items-end gap-1.5">
          <span className="text-5xl font-semibold leading-none tracking-tight text-white [font-variant-numeric:tabular-nums]">
            {Math.round(animatedLatest)}
          </span>
          <span className="mb-1 text-sm text-slate-500">ms</span>
        </div>
        <div className="mb-1 flex gap-4 text-xs text-slate-400">
          <span>
            avg <b className="font-medium text-slate-200">{average}ms</b>
          </span>
          <span>
            peak <b className="font-medium text-slate-200">{peak}ms</b>
          </span>
        </div>
      </div>

      {/* Chart */}
      <div
        className="relative min-h-[130px] flex-1 cursor-crosshair"
        onMouseMove={handleChartMove}
        onMouseLeave={() => setHover(null)}
      >
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full overflow-visible"
          role="img"
          aria-label="Server latency over the last minute"
        >
          <defs>
            <linearGradient id="tb-lat-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#818cf8" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#818cf8" stopOpacity="0" />
            </linearGradient>
          </defs>

          {[25, 50, 75].map((y) => (
            <line key={y} x1="0" x2="100" y1={y} y2={y} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 4" vectorEffect="non-scaling-stroke" />
          ))}

          <path d={area} fill="url(#tb-lat-fill)" />
          <path
            d={line}
            fill="none"
            stroke="#a5b4fc"
            strokeWidth="2.5"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            style={{ filter: "drop-shadow(0 0 6px rgba(129,140,248,0.7))" }}
          />

          {hover !== null && (
            <line x1={points[hover].x} x2={points[hover].x} y1="0" y2="100" stroke="rgba(165,180,252,0.45)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
          )}
        </svg>

        {/* Dot on the point you are reading, plus a tooltip while hovering */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-indigo-200 bg-indigo-500 shadow-[0_0_12px_rgba(129,140,248,0.9)]"
          style={{ left: `${points[shown].x}%`, top: `${points[shown].y}%` }}
        />
        {hover !== null && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg border border-white/10 bg-[#161a2b]/95 px-2.5 py-1.5 text-xs shadow-xl backdrop-blur-md"
            style={{
              left: `clamp(48px, ${points[hover].x}%, calc(100% - 48px))`,
              top: `calc(${points[hover].y}% - 14px)`,
            }}
          >
            <div className="text-slate-400">{Math.round(((series.length - 1 - hover) * TICK_MS) / 1000)}s ago</div>
            <div className="font-medium text-white">{Math.round(series[hover])} ms</div>
          </div>
        )}
      </div>

      <div className="mt-2 flex justify-between text-[11px] text-slate-500">
        <span>{Math.round((SERIES_LENGTH * TICK_MS) / 1000)}s ago</span>
        <span>now</span>
      </div>

      {/* Region pings */}
      <ul className="mt-4 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
        {REGIONS.map((region, i) => {
          const status = statusOf(pings[i]);
          return (
            <li
              key={region.name}
              className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-sm transition-colors duration-200 hover:bg-white/[0.05]"
            >
              <span className={cx("h-2 w-2 shrink-0 rounded-full", status.dot)} />
              <span className="flex-1 text-slate-300">{region.name}</span>
              <span className={cx("text-xs [font-variant-numeric:tabular-nums]", status.text)}>{pings[i]} ms</span>
            </li>
          );
        })}
      </ul>
    </GlowCard>
  );
}

// end of LatencyCard


/* ==========================================================================
   Card 2: Deploy terminal (tall)
   ========================================================================== */

function TerminalCard() {
  // step counts how many script lines have been printed; after the end it waits a moment, then starts over
  const [step, setStep] = useState(1);

  useEffect(() => {
    const id = window.setInterval(() => {
      setStep((s) => (s >= SCRIPT.length + 4 ? 1 : s + 1));
    }, 850);
    return () => window.clearInterval(id);
  }, []);

  const printed = Math.min(step, SCRIPT.length);
  const first = Math.max(0, printed - TERM_VISIBLE);
  const visible = SCRIPT.slice(first, printed);

  return (
    <GlowCard accent="fuchsia" className="min-h-[340px] sm:col-span-2 lg:col-span-1 lg:row-span-2">
      <CardTitle
        right={
          <span className="flex items-center gap-1.5" aria-hidden="true">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-400/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
          </span>
        }
      >
        deploy.sh
      </CardTitle>

      <div
        className="flex flex-1 flex-col justify-end gap-1.5 overflow-hidden rounded-xl border border-white/5 bg-black/30 p-4 font-mono text-xs leading-relaxed"
        aria-label="Deploy log"
        role="log"
      >
        {visible.map((line, i) => {
          const style = LINE_STYLES[line.type];
          const isLast = first + i === printed - 1;
          return (
            <div key={first + i} className="tb-slide flex gap-2">
              <span className={cx("w-3 shrink-0 text-center", style.markClass)}>{style.mark}</span>
              <span className={cx("min-w-0 break-words", style.textClass)}>
                {line.text}
                {isLast && printed < SCRIPT.length && <span className="tb-blink ml-1 inline-block h-3 w-1.5 translate-y-0.5 bg-fuchsia-300" />}
              </span>
            </div>
          );
        })}
      </div>
    </GlowCard>
  );
}

// end of TerminalCard


/* ==========================================================================
   Card 3: Lighthouse scores (small)
   ========================================================================== */

function LighthouseCard() {
  const radius = 20;
  const circumference = 2 * Math.PI * radius;

  return (
    <GlowCard accent="emerald" className="min-h-[200px]">
      <CardTitle>Lighthouse</CardTitle>

      <div className="flex flex-1 items-center justify-between gap-1">
        {LIGHTHOUSE.map((item) => (
          <div key={item.label} className="group flex flex-col items-center gap-2">
            <div className="relative h-14 w-14">
              <svg viewBox="0 0 50 50" className="h-full w-full -rotate-90" aria-hidden="true">
                <circle cx="25" cy="25" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
                <circle
                  cx="25"
                  cy="25"
                  r={radius}
                  fill="none"
                  stroke="#34d399"
                  strokeWidth="4"
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  className="tb-ring transition-[filter] duration-300 group-hover:[filter:drop-shadow(0_0_5px_#34d399)]"
                  style={
                    {
                      "--from": `${circumference}`,
                      "--to": `${circumference * (1 - item.score / 100)}`,
                    } as CSSProperties
                  }
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-white">
                {item.score}
              </span>
            </div>
            <span className="text-[11px] text-slate-500">{item.label}</span>
          </div>
        ))}
      </div>
    </GlowCard>
  );
}

// end of LighthouseCard


/* ==========================================================================
   Card 4: Requests per second (small)
   ========================================================================== */

function ThroughputCard() {
  const [bars, setBars] = useState<number[]>(() =>
    Array.from({ length: 16 }, (_, i) => 1500 + Math.sin(i * 0.8) * 300 + ((i * 53) % 5) * 40)
  );

  useEffect(() => {
    const id = window.setInterval(() => {
      setBars((prev) => [...prev.slice(1), clamp(prev[prev.length - 1] + (Math.random() - 0.45) * 420, 900, 2600)]);
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  const latest = bars[bars.length - 1];
  const animated = useAnimatedNumber(latest, 600);
  const max = Math.max(...bars);

  return (
    <GlowCard accent="cyan" className="min-h-[200px]">
      <CardTitle right={<LiveBadge />}>Requests / sec</CardTitle>

      <div className="text-4xl font-semibold leading-none tracking-tight text-white [font-variant-numeric:tabular-nums]">
        {Math.round(animated).toLocaleString("en-US")}
      </div>

      <div className="mt-auto flex h-14 items-end gap-1" aria-hidden="true">
        {bars.map((v, i) => (
          <span
            key={i}
            className={cx(
              "flex-1 rounded-sm transition-all duration-700 ease-out",
              i === bars.length - 1 ? "bg-cyan-300 shadow-[0_0_10px_rgba(103,232,249,0.8)]" : "bg-cyan-400/30"
            )}
            style={{ height: `${Math.max((v / max) * 100, 8)}%` }}
          />
        ))}
      </div>
    </GlowCard>
  );
}

// end of ThroughputCard


/* ==========================================================================
   Card 5: Tech stack badges (wide)
   ========================================================================== */

export function StackCard({ techs = TECHS, title = "Tech stack", hint = "Hover or tab to a tool to see what we use it for." }: { techs?: Tech[]; title?: string; hint?: string }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = techs.find((t) => t.id === activeId);

  return (
    <GlowCard accent="amber" className="min-h-[200px] sm:col-span-2 lg:col-span-4">
      <CardTitle>{title}</CardTitle>

      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        {techs.map((tech) => {
          const on = tech.id === activeId;
          return (
            <li key={tech.id}>
              <button
                type="button"
                onMouseEnter={() => setActiveId(tech.id)}
                onMouseLeave={() => setActiveId(null)}
                onFocus={() => setActiveId(tech.id)}
                onBlur={() => setActiveId(null)}
                aria-label={`${tech.name} ${tech.version}`}
                className="flex w-full flex-col items-center gap-1.5 rounded-2xl border px-2 py-3 transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300"
                style={{
                  color: on ? `rgb(${tech.rgb})` : "#94a3b8",
                  borderColor: on ? `rgba(${tech.rgb}, 0.55)` : "rgba(255,255,255,0.08)",
                  background: on ? `rgba(${tech.rgb}, 0.1)` : "rgba(255,255,255,0.03)",
                  transform: on ? "translateY(-3px)" : "translateY(0)",
                  boxShadow: on ? `0 10px 30px -10px rgba(${tech.rgb}, 0.5)` : "none",
                }}
              >
                {tech.icon}
                <span className={cx("text-xs font-medium transition-colors duration-300", on ? "text-white" : "text-slate-300")}>
                  {tech.name}
                </span>
                <span className="text-[10px] text-slate-500">{tech.version ? `v${tech.version}` : ""}</span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Description of whichever tool you are pointing at */}
      <p className="mt-4 min-h-[20px] text-sm text-slate-400" aria-live="polite">
        {active ? (
          <span key={active.id} className="tb-fade">
            {active.desc}
          </span>
        ) : (
          hint
        )}
      </p>
    </GlowCard>
  );
}

// end of StackCard


/* ==========================================================================
   Component-scoped CSS so no tailwind.config changes are needed
   ========================================================================== */

export function BentoStyles() {
  return (
    <style>{`
        /* Pulsing "live" dot */
        @keyframes tb-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        .tb-pulse { animation: tb-pulse 1.6s ease-in-out infinite; }

        /* Terminal lines slide up as they appear */
        @keyframes tb-slide {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .tb-slide { animation: tb-slide 0.3s ease both; }

        /* Blinking terminal cursor */
        @keyframes tb-blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        .tb-blink { animation: tb-blink 1s steps(2, start) infinite; }

        /* Score rings fill up */
        @keyframes tb-ring { from { stroke-dashoffset: var(--from); } to { stroke-dashoffset: var(--to); } }
        .tb-ring { animation: tb-ring 1.2s cubic-bezier(0.4, 0, 0.2, 1) both; }

        /* Description text fades in */
        @keyframes tb-fade {
          from { opacity: 0; transform: translateY(3px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .tb-fade { display: inline-block; animation: tb-fade 0.3s ease both; }

        /* Reduced motion: show everything in its final state */
        @media (prefers-reduced-motion: reduce) {
          .tb-pulse, .tb-slide, .tb-blink, .tb-ring, .tb-fade { animation: none; }
        }
      `}</style>
  );
}


/* ==========================================================================
   Main component (the pasted demo: sample numbers, never rendered in Semasa)
   ========================================================================== */

export default function TechStackBento() {
  return (
    <>
      <BentoStyles />

      <section className="w-full bg-[#07080d] px-4 py-14 text-slate-200 sm:px-8 sm:py-20">
        <div className="mx-auto max-w-6xl">
          {/* Heading */}
          <div className="mb-10 max-w-2xl">
            <p className="mb-3 text-xs font-medium uppercase tracking-[0.2em] text-amber-300">Tech stack</p>
            <h2 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">
              Built on tools we trust, watched in real time
            </h2>
            <p className="mt-3 text-slate-400">
              Live numbers from production, the pipeline that ships it and the stack underneath.
            </p>
          </div>

          {/* Grid: 1 column on phones, 2 on tablets, 4 on desktops */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:auto-rows-[210px] lg:grid-cols-4">
            <LatencyCard />
            <TerminalCard />
            <LighthouseCard />
            <ThroughputCard />
            <StackCard />
          </div>
        </div>
      </section>
    </>
  );
}

// end of main component

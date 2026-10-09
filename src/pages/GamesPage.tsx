import { useEffect, useRef, useState } from "react";
import { Play, RotateCcw } from "lucide-react";

/* Games. One is in to prove the stack end to end on a phone (plain canvas + JS, no library); the rest is the list Wan
   and Bernard will fill in. Burger Tap: buns fall, tap them before they hit the counter; 30 seconds; the best score is
   kept on this device. */
const BEST = "bernard.games.burgertap.best";

export default function GamesPage() {
  return (
    <div className="space-y-4 pt-2">
      <div><h1 className="font-display text-3xl font-bold">Games</h1><p className="text-sm text-muted">One to start; more will be added here.</p></div>
      <BurgerTap />
      <div className="grid gap-3 sm:grid-cols-3">
        {["Memory match", "Word scramble", "Quiz night"].map((n) => <div key={n} className="card p-4 opacity-70"><p className="font-display text-lg font-semibold">{n}</p><p className="text-xs text-muted">Coming soon</p></div>)}
      </div>
    </div>
  );
}

function BurgerTap() {
  const ref = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<"idle" | "play" | "over">("idle");
  const [score, setScore] = useState(0);
  const [left, setLeft] = useState(30);
  const [best, setBest] = useState<number>(() => { try { return Number(localStorage.getItem(BEST) || 0); } catch { return 0; } });
  const game = useRef<{ items: { x: number; y: number; v: number; r: number }[]; score: number; t0: number; raf: number; last: number }>({ items: [], score: 0, t0: 0, raf: 0, last: 0 });

  useEffect(() => {
    if (state !== "play") return;
    const c = ref.current!; const ctx = c.getContext("2d")!;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = c.clientWidth, H = c.clientHeight;
    c.width = W * dpr; c.height = H * dpr; ctx.scale(dpr, dpr);
    const g = game.current; g.items = []; g.score = 0; g.t0 = performance.now(); g.last = g.t0;
    const ink = getComputedStyle(document.documentElement).getPropertyValue("--c-line").trim();
    const col = (v: string) => `rgb(${v})`;
    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - g.last) / 1000); g.last = now;
      const elapsed = (now - g.t0) / 1000;
      const remaining = Math.max(0, 30 - elapsed);
      setLeft(Math.ceil(remaining));
      if (Math.random() < 0.02 + elapsed * 0.002) g.items.push({ x: 30 + Math.random() * (W - 60), y: -30, v: 60 + Math.random() * 80 + elapsed * 4, r: 22 });
      for (const it of g.items) it.y += it.v * dt;
      g.items = g.items.filter((it) => it.y < H + 30);
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "rgba(0,0,0,0.04)"; ctx.fillRect(0, H - 14, W, 14);
      for (const it of g.items) {
        // a bun: top dome, a lettuce line, the bottom
        ctx.lineWidth = 3; ctx.strokeStyle = col(ink);
        ctx.fillStyle = "#F4B860"; ctx.beginPath(); ctx.arc(it.x, it.y, it.r, Math.PI, 0); ctx.closePath(); ctx.fill(); ctx.stroke();
        ctx.fillStyle = "#7CB342"; ctx.fillRect(it.x - it.r, it.y, it.r * 2, 6); ctx.strokeRect(it.x - it.r, it.y, it.r * 2, 6);
        ctx.fillStyle = "#F4B860"; ctx.beginPath(); ctx.roundRect(it.x - it.r, it.y + 6, it.r * 2, 10, 5); ctx.fill(); ctx.stroke();
      }
      if (remaining > 0) g.raf = requestAnimationFrame(draw);
      else { setScore(g.score); setState("over"); setBest((b) => { const n = Math.max(b, g.score); try { localStorage.setItem(BEST, String(n)); } catch { /* ignore */ } return n; }); }
    };
    g.raf = requestAnimationFrame(draw);
    const tap = (e: PointerEvent) => {
      const rect = c.getBoundingClientRect(); const x = e.clientX - rect.left, y = e.clientY - rect.top;
      const i = g.items.findIndex((it) => Math.hypot(it.x - x, it.y - y) < it.r + 12);
      if (i >= 0) { g.items.splice(i, 1); g.score += 1; setScore(g.score); }
    };
    c.addEventListener("pointerdown", tap);
    return () => { cancelAnimationFrame(g.raf); c.removeEventListener("pointerdown", tap); };
  }, [state]);

  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b-[3px] border-line bg-surface-2 px-4 py-2">
        <p className="font-display text-xl font-semibold">Burger Tap</p>
        <p className="text-sm"><b>{score}</b> · {left}s · best {best}</p>
      </div>
      <div className="relative h-72 touch-none select-none sm:h-96">
        <canvas ref={ref} className="h-full w-full" aria-label="Burger Tap game board" />
        {state !== "play" && (
          <div className="absolute inset-0 grid place-items-center bg-surface/80 text-center">
            <div>
              {state === "over" && <p className="mb-2 font-display text-2xl font-bold">{score} buns!</p>}
              <p className="mb-3 text-sm text-muted">Tap the buns before they hit the counter. 30 seconds.</p>
              <button type="button" className="btn btn-ketchup" onClick={() => { setScore(0); setLeft(30); setState("play"); }}>{state === "over" ? <RotateCcw size={16} /> : <Play size={16} />} {state === "over" ? "Again" : "Play"}</button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

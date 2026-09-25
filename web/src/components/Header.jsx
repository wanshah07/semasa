import { FileText, Lightbulb, LogOut, Palette, Radio, Settings, Sparkles } from "lucide-react";
import { THEMES, useTheme } from "../design/ThemeProvider";
import { supabase } from "../lib/SupabaseClient";
import Button from "./ui/Button";

export default function Header({ tab, setTab, user }) {
  const { theme, setTheme } = useTheme();
  const tabs = [
    { id: "isu", label: "Isu semasa", icon: Radio },
    { id: "idea", label: "Idea", icon: Lightbulb },
    { id: "post", label: "Post", icon: FileText },
    { id: "media", label: "Makmal media", icon: Sparkles },
    { id: "tetapan", label: "Tetapan", icon: Settings },
  ];
  return (
    <header className="glass sticky top-0 z-40">
      <div className="mx-auto flex max-w-page items-center gap-4 px-4 py-3 sm:px-6">
        <a href="#top" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-tile bg-ink text-bg">
            <span className="h-3 w-3 rounded-full border-2 border-accent" />
          </span>
          <span className="font-display text-lg font-semibold tracking-tight">Semasa</span>
        </a>

        <nav className="ml-2 hidden items-center gap-1 rounded-pill bg-surface-2 p-1 md:flex">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 rounded-pill px-3 py-1.5 text-sm transition ${
                tab === id ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"}`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <label className="flex items-center gap-1.5 rounded-pill border border-line bg-surface px-2.5 py-1.5 text-xs text-muted">
            <Palette size={13} />
            <select value={theme} onChange={(e) => setTheme(e.target.value)}
              className="bg-transparent text-ink outline-none" aria-label="Theme">
              {THEMES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          {user && (
            <Button variant="ghost" size="sm" onClick={() => supabase.auth.signOut()} title={user.email}>
              <LogOut size={13} /> <span className="hidden sm:inline">Keluar</span>
            </Button>
          )}
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-4 pb-2 md:hidden">
        {tabs.map(({ id, label }) => (
          <button key={id} onClick={() => setTab(id)}
            className={`shrink-0 rounded-pill px-3 py-1.5 text-sm ${tab === id ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
            {label}
          </button>
        ))}
      </nav>
    </header>
  );
}

import { FileText, HelpCircle, Lightbulb, ListChecks, LogOut, Palette, Radio, Settings, Sparkles } from "lucide-react";
import { THEMES, useTheme } from "../design/ThemeProvider";
import { supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";

export default function Header({ tab, setTab, user }) {
  const { theme, setTheme } = useTheme();
  const { lang, setLang, t } = useLang();
  const tabs = [
    { id: "isu", label: t("Isu semasa", "Current issues"), icon: Radio },
    { id: "idea", label: t("Idea", "Ideas"), icon: Lightbulb },
    { id: "post", label: t("Post", "Posts"), icon: FileText },
    { id: "media", label: t("Makmal media", "Media lab"), icon: Sparkles },
    { id: "faq", label: "FAQ", icon: HelpCircle },
    { id: "log", label: "Log", icon: ListChecks },
    { id: "tetapan", label: t("Tetapan", "Settings"), icon: Settings },
  ];
  return (
    <header className="glass sticky top-0 z-40">
      <div className="mx-auto flex max-w-page items-center gap-3 px-4 py-3 sm:px-6 xl:gap-4">
        <a href="#top" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-tile bg-ink text-bg">
            <span className="h-3 w-3 rounded-full border-2 border-accent" />
          </span>
          <span className="font-display text-lg font-semibold tracking-tight">Semasa</span>
        </a>

        <nav className="hidden items-center gap-1 rounded-pill bg-surface-2 p-1 xl:ml-2 xl:flex">
          {tabs.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 whitespace-nowrap rounded-pill px-3 py-1.5 text-sm transition ${
                tab === id ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"}`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <div role="group" aria-label={t("Bahasa", "Language")} className="flex rounded-pill border border-line bg-surface p-0.5 text-xs">
            {[["bm", "BM"], ["en", "EN"]].map(([id, label]) => (
              <button key={id} type="button" onClick={() => setLang(id)} aria-pressed={lang === id} data-lang={id}
                title={id === "bm" ? "Bahasa Malaysia" : "English"}
                className={`rounded-pill px-2.5 py-1 font-medium transition ${lang === id ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}>
                {label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 rounded-pill border border-line bg-surface px-2.5 py-1.5 text-xs text-muted">
            <Palette size={13} className="hidden xl:block" />
            <select value={theme} onChange={(e) => setTheme(e.target.value)}
              className="bg-transparent text-ink outline-none" aria-label={t("Tema", "Theme")}>
              {THEMES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          {user && (
            <Button variant="ghost" size="sm" onClick={() => supabase.auth.signOut()} title={`${t("Keluar", "Sign out")} · ${user.email}`}
              aria-label={t("Keluar", "Sign out")}>
              <LogOut size={13} /> <span className="hidden xl:inline">{t("Keluar", "Sign out")}</span>
            </Button>
          )}
        </div>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-4 pb-2 xl:hidden">
        {tabs.map(({ id, label }) => (
          <button key={id} onClick={() => setTab(id)}
            className={`shrink-0 whitespace-nowrap rounded-pill px-3 py-1.5 text-sm ${tab === id ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
            {label}
          </button>
        ))}
      </nav>
    </header>
  );
}

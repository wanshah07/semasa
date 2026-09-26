import { LogOut, Palette, PanelLeftClose, Pin } from "lucide-react";
import { THEMES, useTheme } from "../design/ThemeProvider";
import { supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { tabsOf } from "../lib/tabs";
import Button from "./ui/Button";

/* `sidebar`: the sidebar is showing on a wide screen (App.jsx), so the tabs and the logo live there and the header
   keeps only the language, the theme and the switch between a pinned sidebar and one that hides itself (`navMode`). */
export default function Header({ tab, setTab, user, sidebar = false, navMode = "pinned", onToggleSidebar }) {
  const { theme, setTheme } = useTheme();
  const { lang, setLang, t } = useLang();
  const tabs = tabsOf(t);
  return (
    <header className="glass sticky top-0 z-40">
      <div className="mx-auto flex max-w-page items-center gap-3 px-4 py-3 sm:px-6 xl:gap-4">
        {onToggleSidebar && (() => {
          const auto = navMode === "auto";
          const label = auto ? t("Pin menu tepi (sentiasa tunjuk)", "Pin the sidebar (always show)")
            : t("Auto sembunyi menu tepi (buka bila tuding)", "Auto-hide the sidebar (opens when you point at it)");
          return (
            <button type="button" onClick={onToggleSidebar} data-sidebar-toggle data-mode={navMode} aria-pressed={!auto}
              aria-label={label} title={label}
              className="hidden rounded-tile p-1.5 text-muted transition hover:bg-surface-2 hover:text-ink lg:inline-flex">
              {auto ? <Pin size={18} strokeWidth={1.5} /> : <PanelLeftClose size={18} strokeWidth={1.5} />}
            </button>
          );
        })()}
        <a href="#top" className={`flex items-center gap-2 ${sidebar ? "lg:hidden" : ""}`}>
          <span className="grid h-8 w-8 place-items-center rounded-tile bg-ink text-bg">
            <span className="h-3 w-3 rounded-full border-2 border-accent" />
          </span>
          <span className="font-display text-lg font-semibold tracking-tight">Semasa</span>
        </a>

        {/* eight tabs: it may scroll inside itself, never push the page sideways (1280 px in BM was 4 px too wide) */}
        <nav className={`hidden min-w-0 items-center gap-0.5 overflow-x-auto rounded-pill bg-surface-2 p-1 xl:ml-1 ${sidebar ? "" : "xl:flex"}`}>
          {tabs.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-pill px-2.5 py-1.5 text-sm transition ${
                tab === id ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"}`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-2">
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
              <LogOut size={13} /> <span className="hidden 2xl:inline">{t("Keluar", "Sign out")}</span>
            </Button>
          )}
        </div>
      </div>
      <nav className={`flex gap-1 overflow-x-auto px-4 pb-2 ${sidebar ? "lg:hidden" : "xl:hidden"}`}>
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

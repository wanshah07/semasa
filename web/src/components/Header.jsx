import { LogOut, Menu, Palette, PanelLeftClose, Pin } from "lucide-react";
import { THEMES, useTheme } from "../design/ThemeProvider";
import { supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { tabsOf } from "../lib/tabs";
import Button from "./ui/Button";

/** BM / EN. `big`: the phone menu's version, each button a 44 px target. */
export function LangSwitch({ big = false }) {
  const { lang, setLang, t } = useLang();
  return (
    <div role="group" aria-label={t("Bahasa", "Language")} className={`flex rounded-pill border border-line bg-surface p-0.5 ${big ? "text-sm" : "text-xs"}`}>
      {[["bm", "BM"], ["en", "EN"]].map(([id, label]) => (
        <button key={id} type="button" onClick={() => setLang(id)} aria-pressed={lang === id} data-lang={id}
          title={id === "bm" ? "Bahasa Malaysia" : "English"}
          className={`rounded-pill font-medium transition ${big ? "min-h-[44px] flex-1 px-4" : "px-2.5 py-1"} ${lang === id ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

/** The theme picker. `big`: the phone menu's version, 44 px tall. */
export function ThemeSelect({ big = false }) {
  const { theme, pick, setTheme } = useTheme();
  const { t } = useLang();
  const shown = THEMES.find((x) => x.id === theme)?.label;
  return (
    <label className={`flex items-center gap-1.5 rounded-pill border border-line bg-surface px-2.5 text-muted ${big ? "min-h-[44px] text-sm" : "py-1.5 text-xs"}`}>
      <Palette size={13} className={big ? "" : "hidden xl:block"} />
      <select value={pick} onChange={(e) => setTheme(e.target.value)} data-theme-pick
        title={pick === "auto" ? t(`Ikut peranti: ${shown}`, `Follows the device: ${shown}`) : shown}
        className={`bg-transparent text-ink outline-none ${big ? "min-h-[44px] flex-1" : ""}`} aria-label={t("Tema", "Theme")}>
        {/* the device's light or dark setting decides until a theme is picked; this option hands it back. The theme it
            resolves to goes in the title, not the option: a longer option widened the select past a 390 px phone. */}
        <option value="auto">{t("Ikut peranti", "Follow device")}</option>
        {THEMES.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
      </select>
    </label>
  );
}

/* `sidebar`: the sidebar is showing on a wide screen (App.jsx), so the tabs and the logo live there and the header
   keeps only the language, the theme and the switch between a pinned sidebar and one that hides itself (`navMode`).
   Below lg (phones, the installed iPhone app) the header is one compact row: the labelled Menu button that slides the
   sidebar over the page (`onMenu`), the mark and the guide. Language, theme and sign-out move into that menu, because
   all of them in one row did not fit a 375 px phone. The five most used places are in the bottom bar. */
export default function Header({ tab, setTab, user, sidebar = false, navMode = "auto", onToggleSidebar, onGuide, onMenu }) {
  const { t } = useLang();
  const tabs = tabsOf(t);
  return (
    <header className="app-header glass sticky top-0 z-40">
      <div className="mx-auto flex max-w-page items-center gap-2 px-3 py-1.5 sm:px-6 lg:gap-3 lg:py-3 xl:gap-4">
        {onMenu && (
          <button type="button" onClick={onMenu} data-menu-open aria-haspopup="dialog"
            className="-ml-1 inline-flex min-h-[44px] items-center gap-1.5 rounded-tile px-2.5 text-sm font-medium text-ink transition hover:bg-surface-2 active:bg-surface-2 lg:hidden">
            <Menu size={20} aria-hidden="true" /> Menu
          </button>
        )}
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
        <a href="#top" aria-label="Semasa" className={`flex min-h-[44px] items-center gap-2 ${sidebar ? "lg:hidden" : ""}`}>
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
          <div className={`items-center gap-2 ${onMenu ? "hidden lg:flex" : "flex"}`}>
            <LangSwitch />
            <ThemeSelect />
          </div>
          {onGuide && (
            <button type="button" onClick={onGuide} aria-label={t("Panduan", "Guide")} title={t("Panduan", "Guide")} data-guide
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-line bg-surface text-sm font-semibold text-muted transition hover:bg-surface-2 hover:text-ink lg:h-8 lg:w-8">?</button>
          )}
          {user && (
            <Button variant="ghost" size="sm" onClick={() => supabase.auth.signOut()} title={`${t("Keluar", "Sign out")} · ${user.email}`}
              aria-label={t("Keluar", "Sign out")} className={onMenu ? "hidden lg:inline-flex" : ""}>
              <LogOut size={13} /> <span className="hidden 2xl:inline">{t("Keluar", "Sign out")}</span>
            </Button>
          )}
        </div>
      </div>
      {/* the tab row of a header with no sidebar; on a phone the Menu button and the bottom bar take its place */}
      {!sidebar && !onMenu && (
        <nav className="flex gap-1 overflow-x-auto px-4 pb-2 xl:hidden">
          {tabs.map(({ id, label }) => (
            <button key={id} onClick={() => setTab(id)}
              className={`shrink-0 whitespace-nowrap rounded-pill px-3 py-1.5 text-sm ${tab === id ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>
              {label}
            </button>
          ))}
        </nav>
      )}
    </header>
  );
}

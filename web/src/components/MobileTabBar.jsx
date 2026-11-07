import { useEffect } from "react";
import { useLang } from "../lib/i18n";
import { mobileTabsOf } from "../lib/tabs";

/* The bottom bar on a phone and in the installed app (below lg, 1024 px): five places, each a 56 px tall target; the
   menu button in the header holds the rest. While it is on screen it sets data-tabbar on <html>, which gives
   --tabbar-h a height (index.css), so the page, the toasts and the chat box keep clear of it and of the home indicator. */
export default function MobileTabBar({ tab, setTab }) {
  const { t } = useLang();
  const items = mobileTabsOf(t);
  useEffect(() => {
    document.documentElement.setAttribute("data-tabbar", "");
    return () => document.documentElement.removeAttribute("data-tabbar");
  }, []);
  return (
    <nav aria-label={t("Pintasan", "Shortcuts")} data-mobile-tabbar
      className="mobile-tabbar glass fixed inset-x-0 bottom-0 z-40 border-t border-line lg:hidden">
      <ul className="mx-auto grid max-w-md grid-cols-5">
        {items.map(({ id, label, icon: Icon, match }) => {
          const on = match.includes(tab);
          return (
            <li key={id}>
              <button type="button" onClick={() => setTab(id)} aria-current={on ? "page" : undefined} data-tab={id}
                className={`flex h-14 w-full flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition active:bg-surface-2 ${
                  on ? "text-accent" : "text-muted"}`}>
                <Icon size={20} strokeWidth={on ? 2 : 1.5} aria-hidden="true" />
                <span>{label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

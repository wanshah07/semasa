import { useEffect, useRef, useState } from "react";
import { LogOut, Pin, PinOff, X } from "lucide-react";
import { SidebarNav } from "@/components/ui/dashboard-sidebar";
import { supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { segmentOf, segmentsOf, tabsOf } from "../lib/tabs";
import { LangSwitch, ThemeSelect } from "./Header";
import GlassControl from "./GlassControl";

const OPEN_MS = 120;    // a cursor passing on its way to the page does not open it
const CLOSE_MS = 300;   // a cursor slipping off the edge for a moment does not close it

/* Semasa's main navigation on a wide screen (lg, 1024 px and up), built on the pasted dashboard sidebar
   (components/ui/dashboard-sidebar.tsx). Below that width the header's own tab row stays, as before. The counts are
   what waits for Wan: new ideas to turn into drafts, and drafts to approve.

   Two modes (Wan, 27 Sep 2026: "can make the sidebar auto hide unhide"; auto is the default), switched by the button
   left of the header:
   - pinned: the full menu always shows beside the page;
   - auto:   a 60 px rail of icons; pointing at it (or tabbing into it) slides the full menu out OVER the page, and it
             slides back when the pointer leaves or a tab is chosen. The page never moves. */
export default function AppSidebar({ tab, setTab, user, counts = {}, mode = "auto", onToggleMode, drawerOpen = false, onCloseDrawer }) {
  const { t } = useLang();
  const [peek, setPeek] = useState(false);
  const timer = useRef(null);
  const auto = mode === "auto";
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => { if (!auto) setPeek(false); }, [auto]);
  const later = (v, ms) => { clearTimeout(timer.current); timer.current = setTimeout(() => setPeek(v), ms); };

  const tabs = tabsOf(t);
  // the menu lists SEGMENTS (Wan, 11 Oct 2026); a segment opens its first page, and its other pages show as tabs above the page
  const segs = segmentsOf(t);
  const countOf = (seg) => seg.pages.reduce((n, p) => n + (counts[p.id] || 0), 0);
  // a segment with more than one page lists its pages under it (Wan, 7 Nov 2026: "add subtopic for sidebar"); the group holding
  // the page in view opens by itself, and a one-page segment stays a single row
  const segItem = (seg) => ({ id: `seg:${seg.id}`, title: seg.label, icon: seg.icon, ...(countOf(seg) ? { badge: countOf(seg) } : {}),
    ...(seg.pages.length > 1 ? { children: seg.pages.map((p) => ({ id: p.id, title: p.label, icon: p.icon, ...(counts[p.id] ? { badge: counts[p.id] } : {}) })) } : {}) });
  const item = (x) => ({ id: x.id, title: x.label, icon: x.icon });
  const groups = [{ items: segs.map(segItem) }];
  const here = segmentOf(t, tab);
  // auto-hide on or paused (pinned), from inside the menu as well as the button beside the header
  const modeItem = onToggleMode ? [{ id: "navmode", title: auto ? t("Pin menu (jeda auto-sembunyi)", "Pin the menu (pause auto-hide)") : t("Auto-sembunyi menu", "Auto-hide the menu"),
    icon: auto ? Pin : PinOff }] : [];
  const bottom = [...modeItem, ...tabs.filter((x) => x.segment === "").map(item),
    ...(user ? [{ id: "logout", title: t("Keluar", "Sign out"), icon: LogOut }] : [])];
  const choose = (id) => {
    if (id === "logout") { onCloseDrawer?.(); return supabase.auth.signOut(); }
    if (id === "navmode") { clearTimeout(timer.current); setPeek(false); return onToggleMode?.(); }
    if (id.startsWith("seg:")) {
      const seg = segs.find((x) => `seg:${x.id}` === id);
      if (seg && here?.id !== seg.id) setTab(seg.pages[0].id);     // already inside it: the tabs above the page do the rest
    } else setTab(id);
    if (auto) { clearTimeout(timer.current); setPeek(false); }
    onCloseDrawer?.();
  };
  const nav = (collapsed, cls) => (
    <SidebarNav className={cls} label={t("Menu utama", "Main menu")} activeId={here && here.pages.length === 1 ? `seg:${here.id}` : tab} groups={groups} bottomItems={bottom}
      workspaces={["Semasa"]} plan={user?.email || t("Makmal kandungan ws.regulab", "ws.regulab content lab")}
      collapsed={collapsed} onSelect={choose} />
  );

  const drawer = drawerOpen && (
    <MobileDrawer onClose={onCloseDrawer} label={t("Menu utama", "Main menu")} closeLabel={t("Tutup menu", "Close the menu")}>
      <SidebarNav className="border-none bg-transparent" label={t("Menu utama", "Main menu")}
        activeId={here && here.pages.length === 1 ? `seg:${here.id}` : tab} groups={groups}
        bottomItems={bottom.filter((x) => x.id !== "navmode")}
        workspaces={["Semasa"]} plan={user?.email || t("Makmal kandungan ws.regulab", "ws.regulab content lab")} onSelect={choose} />
    </MobileDrawer>
  );

  if (!auto) {
    return <>{drawer}<aside className="hidden h-screen shrink-0 lg:sticky lg:top-0 lg:block" data-sidebar="pinned">{nav(false, "bg-surface/60")}</aside></>;
  }
  return (
    <>{drawer}<aside className="z-50 hidden h-screen w-[60px] shrink-0 lg:sticky lg:top-0 lg:block" data-sidebar="auto" data-open={peek || undefined}
      onMouseEnter={() => later(true, OPEN_MS)} onMouseLeave={() => later(false, CLOSE_MS)}
      onFocus={() => later(true, 0)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) later(false, 0); }}
      onKeyDown={(e) => { if (e.key === "Escape") { clearTimeout(timer.current); setPeek(false); } }}>
      <div className={`absolute inset-y-0 left-0 overflow-hidden border-r border-line bg-surface transition-[width,box-shadow] duration-200 ease-out ${
        peek ? "w-[260px] shadow-lift" : "w-[60px]"}`}>
        {nav(!peek, "border-none bg-transparent")}
      </div>
    </aside></>
  );
}

/* The same menu on a phone and in the installed iPhone app (below lg): it slides over the page from the left when the
   header's Menu button is pressed, and closes on a choice, on the backdrop, on the close button or on Escape. The page
   underneath does not scroll while it is open, and focus goes back to the Menu button afterwards. Language and theme
   live here on a phone (the header had no room for them). Rows are 44 px tall (index.css, [data-sidebar="drawer"]). */
function MobileDrawer({ onClose, label, closeLabel, children }) {
  const closeRef = useRef(null);
  const closeFn = useRef(onClose);
  closeFn.current = onClose;     // App passes a new function each render; the effect below must run once per opening
  useEffect(() => {
    const back = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") closeFn.current?.(); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      (document.querySelector("[data-menu-open]") || back)?.focus?.();
    };
  }, []);
  return (
    <div className="fixed inset-0 z-[60] lg:hidden" data-sidebar="drawer" role="dialog" aria-modal="true" aria-label={label}>
      <button type="button" tabIndex={-1} aria-hidden="true" onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-ink/40 animate-in fade-in duration-200" />
      <div className="drawer-panel absolute inset-y-0 left-0 flex w-[min(86vw,320px)] flex-col border-r border-line bg-surface shadow-lift animate-in slide-in-from-left duration-200">
        <div className="flex items-center gap-2 px-3 pt-2">
          <div className="flex flex-1 items-center gap-2"><LangSwitch big /></div>
          <button type="button" ref={closeRef} onClick={onClose} aria-label={closeLabel} data-menu-close
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-muted transition hover:bg-surface-2 hover:text-ink">
            <X size={20} />
          </button>
        </div>
        <div className="px-3 pt-2"><ThemeSelect big /></div>
        <div className="px-3 pt-2"><GlassControl big /></div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

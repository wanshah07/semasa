import { useEffect, useRef, useState } from "react";
import { LogOut } from "lucide-react";
import { SidebarNav } from "@/components/ui/dashboard-sidebar";
import { supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { tabsOf } from "../lib/tabs";

const OPEN_MS = 120;    // a cursor passing on its way to the page does not open it
const CLOSE_MS = 300;   // a cursor slipping off the edge for a moment does not close it

/* Semasa's main navigation on a wide screen (lg, 1024 px and up), built on the pasted dashboard sidebar
   (components/ui/dashboard-sidebar.tsx). Below that width the header's own tab row stays, as before. The counts are
   what waits for Wan: new ideas to turn into drafts, and drafts to approve.

   Two modes (Wan, 27 Sep 2026: "can make the sidebar auto hide unhide"; auto is the default), switched by the button
   left of the header:
   - pinned: the full menu always shows beside the page;
   - auto:   a 60 px rail of icons; pointing at it (or tabbing into it) slides the full menu out OVER the page, and it
             slides back when the pointer leaves or a tab is chosen. The page never moves, so Kanvas keeps its width. */
export default function AppSidebar({ tab, setTab, user, counts = {}, mode = "auto" }) {
  const { t } = useLang();
  const [peek, setPeek] = useState(false);
  const timer = useRef(null);
  const auto = mode === "auto";
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => { if (!auto) setPeek(false); }, [auto]);
  const later = (v, ms) => { clearTimeout(timer.current); timer.current = setTimeout(() => setPeek(v), ms); };

  const tabs = tabsOf(t);
  const item = (x) => ({ id: x.id, title: x.label, icon: x.icon, ...(counts[x.id] ? { badge: counts[x.id] } : {}) });
  const groups = [
    { items: tabs.filter((x) => x.group === "").map(item) },
    { heading: t("Cipta", "Create"), items: tabs.filter((x) => x.group === "create").map(item) },
    { heading: t("Rujukan", "Reference"), items: tabs.filter((x) => x.group === "reference").map(item) },
  ];
  const bottom = [...tabs.filter((x) => x.group === "bottom").map(item),
    ...(user ? [{ id: "logout", title: t("Keluar", "Sign out"), icon: LogOut }] : [])];
  const choose = (id) => {
    if (id === "logout") return supabase.auth.signOut();
    setTab(id);
    if (auto) { clearTimeout(timer.current); setPeek(false); }
  };
  const nav = (collapsed, cls) => (
    <SidebarNav className={cls} label={t("Menu utama", "Main menu")} activeId={tab} groups={groups} bottomItems={bottom}
      workspaces={["Semasa"]} plan={user?.email || t("Makmal kandungan ws.regulab", "ws.regulab content lab")}
      collapsed={collapsed} onSelect={choose} />
  );

  if (!auto) {
    return <aside className="hidden h-screen shrink-0 lg:sticky lg:top-0 lg:block" data-sidebar="pinned">{nav(false, "bg-surface/60")}</aside>;
  }
  return (
    <aside className="z-50 hidden h-screen w-[60px] shrink-0 lg:sticky lg:top-0 lg:block" data-sidebar="auto" data-open={peek || undefined}
      onMouseEnter={() => later(true, OPEN_MS)} onMouseLeave={() => later(false, CLOSE_MS)}
      onFocus={() => later(true, 0)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) later(false, 0); }}
      onKeyDown={(e) => { if (e.key === "Escape") { clearTimeout(timer.current); setPeek(false); } }}>
      <div className={`absolute inset-y-0 left-0 overflow-hidden border-r border-line bg-surface transition-[width,box-shadow] duration-200 ease-out ${
        peek ? "w-[260px] shadow-lift" : "w-[60px]"}`}>
        {nav(!peek, "border-none bg-transparent")}
      </div>
    </aside>
  );
}

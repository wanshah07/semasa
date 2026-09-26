import { LogOut } from "lucide-react";
import { SidebarNav } from "@/components/ui/dashboard-sidebar";
import { supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { tabsOf } from "../lib/tabs";

/* Semasa's main navigation on a wide screen (lg, 1024 px and up), built on the pasted dashboard sidebar
   (components/ui/dashboard-sidebar.tsx). Below that width the header's own tab row stays, as before. The counts are
   what waits for Wan: new ideas to turn into drafts, and drafts to approve. */
export default function AppSidebar({ tab, setTab, user, counts = {} }) {
  const { t } = useLang();
  const tabs = tabsOf(t);
  const item = (x) => ({ id: x.id, title: x.label, icon: x.icon, ...(counts[x.id] ? { badge: counts[x.id] } : {}) });
  const groups = [
    { items: tabs.filter((x) => x.group === "").map(item) },
    { heading: t("Cipta", "Create"), items: tabs.filter((x) => x.group === "create").map(item) },
    { heading: t("Rujukan", "Reference"), items: tabs.filter((x) => x.group === "reference").map(item) },
  ];
  const bottom = [...tabs.filter((x) => x.group === "bottom").map(item),
    ...(user ? [{ id: "logout", title: t("Keluar", "Sign out"), icon: LogOut }] : [])];
  return (
    <SidebarNav className="bg-surface/60" label={t("Menu utama", "Main menu")} activeId={tab} groups={groups} bottomItems={bottom}
      workspaces={["Semasa"]} plan={user?.email || t("Makmal kandungan ws.regulab", "ws.regulab content lab")}
      onSelect={(id) => (id === "logout" ? supabase.auth.signOut() : setTab(id))} />
  );
}

import { useEffect, useState } from "react";
import { FolderOpen, Gamepad2, Home, Settings, Table2 } from "lucide-react";
import { type Token, savedToken } from "./lib/google";
import HomePage from "./pages/HomePage";
import DrivePage from "./pages/DrivePage";
import SheetPage from "./pages/SheetPage";
import GamesPage from "./pages/GamesPage";
import SettingsPage from "./pages/SettingsPage";

export const TABS = [
  { id: "home", label: "Home", icon: Home },
  { id: "drive", label: "Drive", icon: FolderOpen },
  { id: "sheet", label: "Sheet", icon: Table2 },
  { id: "games", label: "Games", icon: Gamepad2 },
  { id: "settings", label: "Settings", icon: Settings },
] as const;
type TabId = (typeof TABS)[number]["id"];
const ids = TABS.map((t) => t.id) as string[];

export default function App() {
  const [tab, setTab] = useState<TabId>(() => { const h = location.hash.replace("#", ""); return (ids.includes(h) ? h : "home") as TabId; });
  const [token, setToken] = useState<Token | null>(() => savedToken());
  const [installEvt, setInstallEvt] = useState<any>(null);
  useEffect(() => {
    const onHash = () => { const h = location.hash.replace("#", ""); setTab((ids.includes(h) ? h : "home") as TabId); };
    window.addEventListener("hashchange", onHash);
    const onInstall = (e: Event) => { e.preventDefault(); setInstallEvt(e); };
    window.addEventListener("beforeinstallprompt", onInstall);
    return () => { window.removeEventListener("hashchange", onHash); window.removeEventListener("beforeinstallprompt", onInstall); };
  }, []);
  const go = (id: TabId) => { setTab(id); location.hash = id === "home" ? "" : id; };
  const page = tab === "drive" ? <DrivePage token={token} setToken={setToken} />
    : tab === "sheet" ? <SheetPage token={token} setToken={setToken} />
    : tab === "games" ? <GamesPage />
    : tab === "settings" ? <SettingsPage token={token} setToken={setToken} />
    : <HomePage token={token} setToken={setToken} go={go} installEvt={installEvt} onInstalled={() => setInstallEvt(null)} />;
  return (
    <div className="mx-auto flex min-h-dvh max-w-5xl flex-col">
      <div className="stripe h-3 w-full" aria-hidden />
      <header className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <button type="button" onClick={() => go("home")} className="flex items-center gap-2 wobble">
          <img src="./icon.svg" alt="" className="h-9 w-9 rounded-xl border-[3px] border-line shadow-card" />
          <span className="font-display text-2xl font-bold tracking-tight">Bernard Tan</span>
        </button>
        <nav className="hidden gap-1 sm:flex" aria-label="Main">
          {TABS.map((t) => <button key={t.id} type="button" onClick={() => go(t.id)} aria-current={tab === t.id ? "page" : undefined}
            className={`btn ${tab === t.id ? "btn-mustard" : "btn-plain"} px-3 py-1.5 text-sm`}><t.icon size={16} /> {t.label}</button>)}
        </nav>
      </header>
      <main className="flex-1 px-4 pb-24 sm:px-6 sm:pb-10">{page}</main>
      {/* the phone's tab bar, thumb-reach; hidden on wide screens where the header nav shows */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t-[3px] border-line bg-surface sm:hidden" aria-label="Main (mobile)" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
        <ul className="grid grid-cols-5">
          {TABS.map((t) => <li key={t.id}><button type="button" onClick={() => go(t.id)} aria-current={tab === t.id ? "page" : undefined}
            className={`flex w-full flex-col items-center gap-0.5 py-2 text-[11px] font-semibold ${tab === t.id ? "text-ketchup" : "text-muted"}`}><t.icon size={22} />{t.label}</button></li>)}
        </ul>
      </nav>
    </div>
  );
}

import { Download, FolderOpen, Gamepad2, Table2 } from "lucide-react";
import { type Token } from "../lib/google";
import Connect from "../components/Connect";

export default function HomePage({ token, setToken, go, installEvt, onInstalled }: { token: Token | null; setToken: (t: Token) => void; go: (id: any) => void; installEvt: any; onInstalled: () => void }) {
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const standalone = typeof window !== "undefined" && (window.matchMedia?.("(display-mode: standalone)").matches || (navigator as any).standalone);
  return (
    <div className="space-y-6 pt-2">
      <section className="card overflow-hidden">
        <div className="stripe h-2" aria-hidden />
        <div className="p-6 sm:p-8">
          <p className="text-xs font-bold uppercase tracking-widest text-muted">Welcome</p>
          <h1 className="mt-1 font-display text-3xl font-bold sm:text-4xl">{greet}, {token?.name?.split(" ")[0] || "Bernard"}.</h1>
          <p className="mt-2 max-w-xl text-sm text-muted">Your Drive, your Sheets and your games, on phone, tablet and desktop. Everything Google here runs in your own account.</p>
          {!token && <div className="mt-5"><Connect setToken={setToken} what="Your Drive and Sheets" /></div>}
          {token && <p className="mt-4 flex items-center gap-2 text-sm">{token.picture && <img src={token.picture} alt="" className="h-7 w-7 rounded-full border-2 border-line" />}Connected as <b>{token.email}</b></p>}
        </div>
      </section>
      <div className="grid gap-4 sm:grid-cols-3">
        {[{ id: "drive", icon: FolderOpen, title: "Drive", text: "Your latest files, a search, open in one tap.", tone: "bg-sky" },
          { id: "sheet", icon: Table2, title: "Sheet", text: "Open a spreadsheet, read a tab, add a row.", tone: "bg-lettuce" },
          { id: "games", icon: Gamepad2, title: "Games", text: "Burger Tap is in; more to come.", tone: "bg-mustard" }].map((c) => (
          <button key={c.id} type="button" onClick={() => go(c.id)} className="card wobble p-5 text-left">
            <span className={`inline-flex h-11 w-11 items-center justify-center rounded-tile border-[3px] border-line ${c.tone} text-ink`}><c.icon size={22} /></span>
            <p className="mt-3 font-display text-xl font-semibold">{c.title}</p>
            <p className="text-sm text-muted">{c.text}</p>
          </button>
        ))}
      </div>
      {!standalone && (
        <section className="card p-5">
          <p className="font-display text-lg font-semibold">Put it on your home screen</p>
          {installEvt ? <button type="button" className="btn btn-mustard mt-2" onClick={async () => { installEvt.prompt(); await installEvt.userChoice; onInstalled(); }}><Download size={16} /> Install app</button>
            : <p className="mt-1 text-sm text-muted">iPhone/iPad: Share → <b>Add to Home Screen</b>. Android/Chrome: menu → <b>Install app</b>. Desktop Chrome/Edge: the install icon in the address bar.</p>}
        </section>
      )}
    </div>
  );
}

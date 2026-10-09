import { useState } from "react";
import { LogOut, Moon, Sun } from "lucide-react";
import { type Token, clientId, setClientId, signOut } from "../lib/google";

export default function SettingsPage({ token, setToken }: { token: Token | null; setToken: (t: Token | null) => void }) {
  const [id, setId] = useState(clientId());
  const [theme, setTheme] = useState(() => document.documentElement.getAttribute("data-theme") || "day");
  const [saved, setSaved] = useState(false);
  const flip = () => { const next = theme === "night" ? "day" : "night"; setTheme(next); document.documentElement.setAttribute("data-theme", next); try { localStorage.setItem("bernard.theme", next); } catch { /* ignore */ } };
  return (
    <div className="space-y-4 pt-2">
      <h1 className="font-display text-3xl font-bold">Settings</h1>
      <section className="card p-5">
        <p className="font-display text-lg font-semibold">Look</p>
        <button type="button" className="btn btn-plain mt-2" onClick={flip}>{theme === "night" ? <Sun size={16} /> : <Moon size={16} />} {theme === "night" ? "Day mode" : "Night mode"}</button>
      </section>
      <section className="card p-5">
        <p className="font-display text-lg font-semibold">Google</p>
        {token ? <p className="mt-1 text-sm">Connected as <b>{token.email}</b> <button type="button" className="btn btn-plain ml-2 px-3 py-1 text-xs" onClick={() => { signOut(token); setToken(null); }}><LogOut size={14} /> Disconnect</button></p>
          : <p className="mt-1 text-sm text-muted">Not connected. Connect from Home, Drive or Sheet.</p>}
        <label className="mt-4 block text-xs font-semibold text-muted">OAuth client id (public; from Google Cloud → Credentials, see README)
          <input value={id} onChange={(e) => { setId(e.target.value); setSaved(false); }} placeholder="1234567890-abc.apps.googleusercontent.com" className="mt-1 w-full rounded-tile border-[3px] border-line bg-surface px-3 py-2 text-sm text-ink" /></label>
        <button type="button" className="btn btn-mustard mt-2 text-sm" onClick={() => { setClientId(id); setSaved(true); }}>Save</button>
        {saved && <span className="ml-2 text-xs text-ok">Saved on this device.</span>}
      </section>
      <section className="card p-5 text-sm text-muted">
        <p className="font-display text-lg font-semibold text-ink">About</p>
        <p className="mt-1">bernardtan.kkmhalalconsultant.com · React + Tailwind + plain CSS/JS · installable on phone, tablet and desktop. Google data stays in your account; this app keeps only a one-hour key in this browser tab.</p>
      </section>
    </div>
  );
}

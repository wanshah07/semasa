import { useEffect, useState } from "react";
import { ExternalLink, RefreshCw, Search } from "lucide-react";
import { type DriveFile, type Token, listFiles } from "../lib/google";
import Connect from "../components/Connect";

const kind = (m: string) => m.includes("spreadsheet") ? "Sheet" : m.includes("document") ? "Doc" : m.includes("presentation") ? "Slides" : m.includes("folder") ? "Folder" : m.startsWith("image/") ? "Image" : m === "application/pdf" ? "PDF" : "File";

export default function DrivePage({ token, setToken }: { token: Token | null; setToken: (t: Token) => void }) {
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = async (query = q) => {
    if (!token) return;
    setBusy(true); setErr("");
    try { setFiles(await listFiles(token, query)); } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(false); }
  };
  useEffect(() => { if (token) load(""); }, [token]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!token) return <div className="pt-6"><Connect setToken={setToken} what="Your Drive" /></div>;
  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="font-display text-3xl font-bold">Drive</h1><p className="text-sm text-muted">Newest first. Tap a file to open it in Google.</p></div>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); load(); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name…" className="rounded-pill border-[3px] border-line bg-surface px-4 py-2 text-sm outline-none" />
          <button type="submit" className="btn btn-mustard px-3" aria-label="Search"><Search size={16} /></button>
          <button type="button" className="btn btn-plain px-3" aria-label="Refresh" onClick={() => { setQ(""); load(""); }}><RefreshCw size={16} className={busy ? "animate-spin" : ""} /></button>
        </form>
      </div>
      {err && <p className="rounded-tile border-[3px] border-danger bg-surface p-3 text-sm text-danger">{err}</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {files.map((f) => (
          <li key={f.id}><a href={f.webViewLink || `https://drive.google.com/open?id=${f.id}`} target="_blank" rel="noreferrer" className="card flex items-center gap-3 p-3 hover:shadow-lift">
            {f.iconLink ? <img src={f.iconLink.replace("/16/", "/32/")} alt="" className="h-8 w-8" /> : <span className="h-8 w-8 rounded bg-surface-2" />}
            <span className="min-w-0 flex-1"><span className="block truncate font-semibold">{f.name}</span>
              <span className="block text-xs text-muted">{kind(f.mimeType)}{f.modifiedTime ? ` · ${new Date(f.modifiedTime).toLocaleDateString("en-MY", { day: "2-digit", month: "short", year: "numeric" })}` : ""}</span></span>
            <ExternalLink size={16} className="shrink-0 text-muted" />
          </a></li>
        ))}
        {!files.length && !busy && <li className="text-sm text-muted">{q ? "Nothing with that name." : "No files yet."}</li>}
      </ul>
    </div>
  );
}

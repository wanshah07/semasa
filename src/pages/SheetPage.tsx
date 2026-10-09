import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import { type DriveFile, type Token, appendRow, listFiles, readTab, sheetTabs } from "../lib/google";
import { num, sheetIdOf, toRow } from "../lib/sheet.js";
import Connect from "../components/Connect";

const KEY = "bernard.sheet.last";

export default function SheetPage({ token, setToken }: { token: Token | null; setToken: (t: Token) => void }) {
  const [sheets, setSheets] = useState<DriveFile[]>([]);
  const [pasted, setPasted] = useState("");
  const [id, setId] = useState<string>(() => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } });
  const [title, setTitle] = useState("");
  const [tabs, setTabs] = useState<string[]>([]);
  const [tab, setTab] = useState("");
  const [data, setData] = useState<{ headers: string[]; rows: any[] }>({ headers: [], rows: [] });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const run = async (what: string, fn: () => Promise<void>) => { setBusy(what); setErr(""); try { await fn(); } catch (e: any) { setErr(e.message || String(e)); } finally { setBusy(""); } };

  useEffect(() => { if (token) run("list", async () => setSheets((await listFiles(token, "")).filter((f) => f.mimeType.includes("spreadsheet")))); }, [token]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!token || !id) return;
    run("open", async () => {
      const meta = await sheetTabs(token, id);
      setTitle(meta.title); setTabs(meta.tabs); setTab(meta.tabs[0] || "");
      try { localStorage.setItem(KEY, id); } catch { /* ignore */ }
    });
  }, [token, id]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (token && id && tab) run("read", async () => setData(await readTab(token, id, tab))); }, [token, id, tab]);   // eslint-disable-line react-hooks/exhaustive-deps

  const sums = useMemo(() => data.headers.map((h) => { const vals = data.rows.map((r) => num(r[h])).filter((v) => v != null) as number[]; return vals.length && vals.length >= data.rows.length / 2 ? vals.reduce((a, b) => a + b, 0) : null; }), [data]);
  if (!token) return <div className="pt-6"><Connect setToken={setToken} what="Your Sheets" /></div>;
  return (
    <div className="space-y-4 pt-2">
      <div><h1 className="font-display text-3xl font-bold">Sheet</h1><p className="text-sm text-muted">Pick one of your spreadsheets, or paste a link. Read a tab, add a row.</p></div>
      <div className="card p-4">
        <div className="flex flex-wrap gap-2">
          <select value={id} onChange={(e) => setId(e.target.value)} className="min-w-0 flex-1 rounded-pill border-[3px] border-line bg-surface px-3 py-2 text-sm">
            <option value="">{busy === "list" ? "Loading your sheets…" : "Choose a spreadsheet…"}</option>
            {sheets.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const v = sheetIdOf(pasted); if (v) { setId(v); setPasted(""); } else setErr("That is not a Google Sheets link or id."); }}>
            <input value={pasted} onChange={(e) => setPasted(e.target.value)} placeholder="…or paste a Sheets link" className="rounded-pill border-[3px] border-line bg-surface px-3 py-2 text-sm" />
            <button type="submit" className="btn btn-plain px-3 text-sm">Open</button>
          </form>
        </div>
        {id && <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="font-display text-lg font-semibold">{title || "…"}</span>
          {tabs.map((t) => <button key={t} type="button" onClick={() => setTab(t)} className={`rounded-pill border-[3px] border-line px-3 py-1 text-xs font-semibold ${tab === t ? "bg-mustard" : "bg-surface"}`}>{t}</button>)}
          <button type="button" className="btn btn-plain px-2 py-1 text-xs" onClick={() => run("read", async () => setData(await readTab(token, id, tab)))} aria-label="Refresh"><RefreshCw size={14} className={busy === "read" ? "animate-spin" : ""} /></button>
          <a href={`https://docs.google.com/spreadsheets/d/${id}`} target="_blank" rel="noreferrer" className="text-xs underline">Open in Google Sheets</a>
        </div>}
      </div>
      {err && <p className="rounded-tile border-[3px] border-danger bg-surface p-3 text-sm text-danger">{err}</p>}
      {id && data.headers.length > 0 && (
        <>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-2 text-left text-xs uppercase tracking-wider"><tr>{data.headers.map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
              <tbody>
                {data.rows.map((r) => <tr key={r.__row} className="border-t-2 border-line/20">{data.headers.map((h) => <td key={h} className="px-3 py-2">{String(r[h] ?? "")}</td>)}</tr>)}
                {!data.rows.length && <tr><td colSpan={data.headers.length} className="px-3 py-6 text-center text-muted">Only a header row so far.</td></tr>}
              </tbody>
              {sums.some((s) => s != null) && <tfoot className="border-t-[3px] border-line bg-surface-2 text-xs font-bold"><tr>{sums.map((s, i) => <td key={i} className="px-3 py-2">{s != null ? `Σ ${s.toLocaleString("en-MY", { maximumFractionDigits: 2 })}` : ""}</td>)}</tr></tfoot>}
            </table>
          </div>
          <form className="card p-4" onSubmit={(e) => { e.preventDefault(); run("add", async () => { await appendRow(token, id, tab, toRow(data.headers, draft)); setDraft({}); setData(await readTab(token, id, tab)); }); }}>
            <p className="mb-2 font-display text-lg font-semibold">Add a row</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {data.headers.map((h) => <label key={h} className="text-xs font-semibold text-muted">{h}<input value={draft[h] || ""} onChange={(e) => setDraft({ ...draft, [h]: e.target.value })} className="mt-1 w-full rounded-tile border-[3px] border-line bg-surface px-3 py-2 text-sm text-ink" /></label>)}
            </div>
            <button type="submit" className="btn btn-ketchup mt-3" disabled={busy === "add"}><Plus size={16} /> {busy === "add" ? "Adding…" : "Add row"}</button>
          </form>
        </>
      )}
    </div>
  );
}

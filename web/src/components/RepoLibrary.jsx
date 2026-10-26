import { useMemo, useState } from "react";
import { AlertTriangle, BookOpen, CheckCircle2, ExternalLink, Loader2, Plus, RefreshCw, ShieldAlert, ShieldCheck, Star, Trash2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { CATEGORY_WORDS, SAFETY_WORDS, STATUS_WORDS, canonicalUrl, categoriesOf, filterRows, flagsOf, groupByCategory, librarySummary, parseRepoUrl } from "../lib/repoLibrary";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { Input, Select } from "./ui/Field";

/* Pustaka repo (Wan, 23 Oct 2026: "add REPO segment, I will add repo link and AI will analyze and ensure it safe and make
   summary and categorize, for example motion repo in motion category, so for AI brain make it separately"). Wan pastes a
   GitHub link; the row lands as `pending`; the database wakes the worker, which reads the repo (never clones or runs it),
   runs the static safety checks, and asks the AI for a summary, category, tags and a verdict. The page draws the library
   grouped by category, lets Wan re-file a repo (his category survives a re-read), re-check it, or remove it. */

const SAFETY_CLS = { safe: "bg-ok/15 text-ok", caution: "bg-warn/15 text-warn", avoid: "bg-danger/15 text-danger", unknown: "bg-surface-2 text-muted" };
const SAFETY_ICON = { safe: ShieldCheck, caution: AlertTriangle, avoid: ShieldAlert, unknown: ShieldCheck };
const STATUS_CLS = { pending: "bg-warn/15 text-warn", working: "bg-accent/15 text-accent", done: "bg-ok/15 text-ok", error: "bg-danger/15 text-danger" };

export default function RepoLibrary({ settings, user, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 1 : 0;
  const w = (v) => (Array.isArray(v) ? v[L] : v);
  const libT = useTable(TABLES.repoLibrary, { enabled: true, order: "updated_at", limit: 500, realtime: true, everyMs: 120_000 });
  const cats = useMemo(() => categoriesOf(settings), [settings]);
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [safety, setSafety] = useState("");
  const [busy, setBusy] = useState("");
  const missing = /semasa_repo_library/.test(libT.error || "");
  const rows = useMemo(() => filterRows(libT.rows, { q, category: cat, safety }), [libT.rows, q, cat, safety]);
  const groups = useMemo(() => groupByCategory(rows, cats), [rows, cats]);
  const sum = useMemo(() => librarySummary(libT.rows), [libT.rows]);

  const add = async () => {
    const full = parseRepoUrl(url);
    if (!full) { onToast?.(t("Tampal pautan github.com/owner/nama.", "Paste a github.com/owner/name link."), "warn"); return; }
    setBusy("add");
    try {
      const { error } = await supabase.from(TABLES.repoLibrary).insert({ url: canonicalUrl(url), full_name: full, note: note.trim(), status: "pending", created_by: user?.id || null });
      if (error) throw new Error(/duplicate|unique/i.test(errText(error)) ? t("Repo ini sudah ada dalam pustaka.", "This repo is already in the library.") : errText(error));
      setUrl(""); setNote("");
      onToast?.(t("Ditambah: Semasa membaca {r} sebentar lagi.", "Added: Semasa reads {r} shortly.", { r: full }), "ok");
      libT.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const patch = async (r, fields, okWord) => {
    setBusy(r.id);
    try {
      const { error } = await supabase.from(TABLES.repoLibrary).update(fields).eq("id", r.id);
      if (error) throw new Error(errText(error));
      if (okWord) onToast?.(okWord, "ok");
      libT.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };
  const remove = async (r) => {
    setBusy(r.id);
    try {
      const { error } = await supabase.from(TABLES.repoLibrary).delete().eq("id", r.id);
      if (error) throw new Error(errText(error));
      libT.reload();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(""); }
  };

  return (
    <section className="mb-8" data-repo-library>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-display text-2xl"><BookOpen size={18} className="text-accent" /> {t("Pustaka repo", "Repo library")}</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Tampal pautan GitHub untuk apa-apa fungsi (bukan video sahaja): Semasa membaca repo itu (tidak pernah dijalankan), semak keselamatan, senaraikan fungsinya, tulis ringkasan dan failkan ikut kategori. Semakan ialah bacaan, bukan audit.",
            "Paste a GitHub link for any function (not only video): Semasa reads the repo (never runs it), checks it for safety, lists what it can do, writes a summary and files it by category. The check is a reading, not an audit.")}</p>
        </div>
        <p className="text-xs text-muted">{sum.total} {t("repo", "repos")} · {sum.done} {t("siap", "done")}{sum.pending ? ` · ${sum.pending} ${t("menunggu", "waiting")}` : ""}{sum.avoid ? ` · ${sum.avoid} ${t("elakkan", "avoid")}` : ""}</p>
      </div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/042_repo_library.sql sekali.", "The table is not there yet: run supabase/042_repo_library.sql once.")}</p>}
      {libT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{libT.error}</p>}

      <Card className="mb-4 p-4">
        <div className="grid gap-2 sm:grid-cols-[2fr_2fr_auto] sm:items-end">
          <label className="block"><span className="mb-1 block text-xs font-medium text-muted">{t("Pautan GitHub", "GitHub link")}</span>
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/owner/nama" onKeyDown={(e) => e.key === "Enter" && add()} /></label>
          <label className="block"><span className="mb-1 block text-xs font-medium text-muted">{t("Nota (pilihan)", "Note (optional)")}</span>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("cth: untuk apa repo ini nanti", "e.g. what you want it for")} /></label>
          <Button onClick={add} disabled={busy === "add" || !url.trim()}>{busy === "add" ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} {t("Tambah", "Add")}</Button>
        </div>
      </Card>

      {libT.rows.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari…", "Search…")} className="!w-56" />
          <Select value={safety} onChange={setSafety} options={[["", t("Semua keselamatan", "Any safety")], ...["safe", "caution", "avoid", "unknown"].map((k) => [k, w(SAFETY_WORDS[k])])]} />
          <button type="button" onClick={() => setCat("")} className={`rounded-pill px-3 py-1 text-xs ${!cat ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>{t("Semua", "All")}</button>
          {cats.filter((c) => libT.rows.some((r) => r.category === c)).map((c) => (
            <button key={c} type="button" onClick={() => setCat(cat === c ? "" : c)} className={`rounded-pill px-3 py-1 text-xs ${cat === c ? "bg-ink text-bg" : "bg-surface-2 text-muted"}`}>{w(CATEGORY_WORDS[c] || c)}</button>
          ))}
        </div>
      )}

      {!libT.loading && !libT.error && !libT.rows.length && (
        <p className="rounded-tile bg-surface-2 p-3 text-sm text-muted">{t("Pustaka kosong. Tampal pautan pertama di atas.", "The library is empty. Paste the first link above.")}</p>
      )}

      {groups.map((g) => (
        <div key={g.category} className="mb-6" data-repo-category={g.category}>
          <h3 className="mb-2 text-xs font-medium text-muted">{w(CATEGORY_WORDS[g.category] || g.category)} · {g.rows.length}</h3>
          <div className="grid gap-3 md:grid-cols-2 [&>*]:min-w-0">
            {g.rows.map((r) => {
              const S = SAFETY_ICON[r.safety] || ShieldCheck;
              const flags = flagsOf(r);
              return (
                <Card key={r.id} className="p-4" data-repo-row>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <a href={r.html_url || r.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1.5 font-display text-lg hover:underline"><span className="[overflow-wrap:anywhere]">{r.name || r.full_name || r.url}</span><ExternalLink size={12} className="shrink-0 text-muted" /></a>
                      <p className="text-xs text-muted [overflow-wrap:anywhere]">{r.full_name}{r.language ? ` · ${r.language}` : ""}{r.license ? ` · ${r.license}` : r.status === "done" ? ` · ${t("tiada lesen", "no licence")}` : ""}{r.stars ? <> · <Star size={10} className="inline" /> {r.stars}</> : ""}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${SAFETY_CLS[r.safety] || SAFETY_CLS.unknown}`}><S size={11} /> {w(SAFETY_WORDS[r.safety] || SAFETY_WORDS.unknown)}</span>
                      {r.status !== "done" && <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${STATUS_CLS[r.status]}`}>{r.status === "working" && <Loader2 size={10} className="animate-spin" />}{w(STATUS_WORDS[r.status] || [r.status, r.status])}</span>}
                    </div>
                  </div>
                  {r.status === "done" && <p className="mt-2 text-sm">{(L ? r.summary_en : r.summary_bm) || r.summary_en || r.summary_bm || r.description || t("(tiada ringkasan)", "(no summary)")}</p>}
                  {r.status === "done" && r.functions?.length > 0 && (
                    <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs [overflow-wrap:anywhere]" data-repo-functions>{r.functions.map((f, i) => <li key={i}>{f}</li>)}</ul>
                  )}
                  {r.status === "done" && r.use_for && r.use_for !== "none" && <p className="mt-1 text-xs text-muted"><CheckCircle2 size={11} className="mr-1 inline text-ok" />{r.use_for}</p>}
                  {r.error && <p className="mt-2 rounded-tile bg-danger/10 p-2 text-xs text-danger">{r.error}</p>}
                  {flags.length > 0 && (
                    <details className="mt-2 text-xs">
                      <summary className="cursor-pointer text-muted">{t("{n} perkara disemak", "{n} things noted", { n: flags.length })}</summary>
                      <ul className="mt-1 space-y-0.5">{flags.map((f, i) => <li key={i} className={f.severity === "avoid" ? "text-danger" : f.severity === "caution" ? "text-warn" : "text-muted"}><b>{f.code}</b> · {f.where}: {f.detail}</li>)}</ul>
                    </details>
                  )}
                  {r.how_to_run && <details className="mt-1 text-xs"><summary className="cursor-pointer text-muted">{t("Cara jalankan", "How to run")}</summary><p className="mt-1 whitespace-pre-wrap text-muted">{r.how_to_run}</p></details>}
                  {r.tags?.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{r.tags.map((x) => <span key={x} className="rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] text-muted">{x}</span>)}</div>}
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Select value={r.category || "lain"} disabled={busy === r.id} onChange={(v) => patch(r, { category: v, category_by: "wan" }, t("Difailkan di {c}.", "Filed under {c}.", { c: w(CATEGORY_WORDS[v] || v) }))}
                      options={cats.map((c) => [c, w(CATEGORY_WORDS[c] || c)])} />
                    <Button size="sm" variant="ghost" disabled={busy === r.id || r.status === "working"} onClick={() => patch(r, { status: "pending", attempts: 0, error: "" }, t("Disemak semula sebentar lagi.", "Re-checking shortly."))}><RefreshCw size={12} /> {t("Semak semula", "Re-check")}</Button>
                    <Button size="sm" variant="ghost" disabled={busy === r.id} onClick={() => remove(r)}><Trash2 size={12} /> {t("Buang", "Remove")}</Button>
                    <span className="ml-auto text-[11px] text-muted">{r.checked_at ? `${t("dibaca", "read")} ${timeAgo(r.checked_at)}` : ""}{r.category_by === "wan" ? ` · ${t("kategori anda", "your category")}` : ""}</span>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      ))}
    </section>
  );
}

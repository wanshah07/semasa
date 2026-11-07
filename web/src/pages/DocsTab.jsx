import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, ExternalLink, FileText, Folder, ListTree, Loader2, Search } from "lucide-react";
import { fadeUp } from "../design/motion";
import { useLang } from "../lib/i18n";
import { parseMarkdown } from "../lib/markdown";
import { changedDate, groupDocs, listDocs, outlineOf, searchDocs, sizeText } from "../lib/repoDocs";
import { LOADERS, META } from "../lib/repoDocsFiles";
import Markdown from "../components/Markdown";
import Card from "../components/ui/Card";
import { Input } from "../components/ui/Field";

/* Rujukan → Dokumen (Wan, 7 Nov 2026: ".md files in reference segment so it auto update"). The repo's own Markdown (CLAUDE.md,
   the READMEs, rules/, ops/, docs/, the skills), bundled at build time by lib/repoDocsFiles.js. A merge to main that changes a .md
   file redeploys the site (pages.yml), so what is shown here is what main says, with nothing to copy by hand. Read only: the file
   is changed in the repo, never here. Drawn with the chat's own Markdown reader, which never passes HTML through. */
const DOCS = listDocs(Object.keys(LOADERS), META);
const REMEMBER = "semasa.view.docs";
const GITHUB = "https://github.com/wanshah07/semasa/blob/main/";

const remembered = () => { try { return window.localStorage.getItem(REMEMBER) || ""; } catch { return ""; } };

export default function DocsTab() {
  const { t, lang } = useLang();
  const [path, setPath] = useState(() => {
    const r = remembered();
    return DOCS.some((d) => d.path === r) ? r : (DOCS.find((d) => d.path === "CLAUDE.md") || DOCS[0])?.path || "";
  });
  const [texts, setTexts] = useState({});          // { path: text } for every file read so far
  const [q, setQ] = useState("");
  const [loadingAll, setLoadingAll] = useState(false);
  const [err, setErr] = useState("");
  const [listOpen, setListOpen] = useState(false);   // phone: the list replaces the document until one is picked
  const top = useRef(null);

  const doc = DOCS.find((d) => d.path === path) || null;
  const text = doc ? texts[doc.path] : undefined;

  async function read(p) {
    const d = DOCS.find((x) => x.path === p);
    if (!d || texts[p] != null) return texts[p];
    const body = await LOADERS[d.key]();
    setTexts((m) => ({ ...m, [p]: String(body ?? "") }));
    return body;
  }

  useEffect(() => {
    if (!path) return;
    setErr("");
    read(path).catch((e) => setErr(String(e?.message || e)));
    try { window.localStorage.setItem(REMEMBER, path); } catch { /* private window: the page opens on CLAUDE.md */ }
  }, [path]); // eslint-disable-line react-hooks/exhaustive-deps

  // Searching the words inside the files needs them all; they are fetched once, on the first query long enough to mean something.
  const wantAll = q.trim().length >= 3;
  useEffect(() => {
    if (!wantAll || loadingAll || DOCS.every((d) => texts[d.path] != null)) return;
    setLoadingAll(true);
    Promise.all(DOCS.map((d) => (texts[d.path] != null ? [d.path, texts[d.path]] : LOADERS[d.key]().then((b) => [d.path, String(b ?? "")]))))
      .then((pairs) => setTexts((m) => ({ ...m, ...Object.fromEntries(pairs) })))
      .catch((e) => setErr(String(e?.message || e)))
      .finally(() => setLoadingAll(false));
  }, [wantAll]); // eslint-disable-line react-hooks/exhaustive-deps

  const found = useMemo(() => searchDocs(DOCS, q, texts), [q, texts]);
  const groups = useMemo(() => groupDocs(found), [found]);
  const tree = useMemo(() => (text != null ? parseMarkdown(text, { softBreak: "space" }) : null), [text]);   // the repo's .md files are hard-wrapped: a newline is the wrap, not a break
  const outline = useMemo(() => (tree ? outlineOf(tree) : []), [tree]);

  function open(p) {
    setPath(p);
    setListOpen(false);
    top.current?.scrollIntoView({ block: "start" });
  }

  const groupName = (g) => (g ? g : t("Akar repo", "Repository root"));
  const when = doc?.changed ? changedDate(doc.changed, lang) : "";

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6" data-docs>
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6">
        <h1 className="font-display text-3xl">{t("Dokumen", "Documents")}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{t(
          `Fail Markdown repo ini (${DOCS.length}): peraturan, nota ops, README dan kemahiran. Dikemas kini sendiri setiap kali main berubah. Untuk mengubah, sunting fail dalam repo.`,
          `This repo's Markdown files (${DOCS.length}): rules, ops notes, READMEs and skills. They update by themselves whenever main changes. To change one, edit the file in the repo.`)}</p>
      </motion.div>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]" ref={top}>
        <Card className={`p-3 lg:sticky lg:top-20 lg:block lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto ${listOpen || !doc ? "" : "hidden"}`} data-docs-list>
          <label className="relative block">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari nama atau isi", "Search names or contents")}
              className="pl-8" aria-label={t("Cari dokumen", "Search documents")} data-docs-search />
          </label>
          {loadingAll && <p className="mt-2 flex items-center gap-1 text-[11px] text-muted"><Loader2 size={12} className="animate-spin" /> {t("Membaca semua fail untuk carian…", "Reading every file for the search…")}</p>}
          {groups.length === 0 && <p className="mt-3 text-xs text-muted">{t("Tiada dokumen sepadan.", "No document matches.")}</p>}
          {groups.map((g) => (
            <section key={g.group || "root"} className="mt-3">
              <h2 className="mb-1 flex items-center gap-1 font-mono text-[11px] text-muted"><Folder size={12} aria-hidden /> {groupName(g.group)}</h2>
              <ul className="space-y-0.5">
                {g.docs.map((d) => (
                  <li key={d.path}>
                    <button type="button" onClick={() => open(d.path)} title={d.path} aria-current={d.path === path ? "page" : undefined}
                      className={`w-full rounded-tile px-2 py-1 text-left text-sm ${d.path === path ? "bg-surface-2 text-ink" : "text-muted hover:bg-surface-2 hover:text-ink"}`}>
                      <span className="flex items-center gap-1.5"><FileText size={13} className="shrink-0" aria-hidden /> <span className="truncate">{d.title}</span>
                        {d.hits > 0 && <span className="ml-auto shrink-0 text-[10px] text-muted">{d.hits}×</span>}</span>
                      {d.snippet && <span className="mt-0.5 block text-[11px] leading-snug text-muted [overflow-wrap:anywhere]">{d.snippet}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </Card>

        <div className={`min-w-0 ${listOpen ? "hidden lg:block" : ""}`}>
          {!doc && <Card className="p-6 text-sm text-muted">{t("Tiada dokumen dalam binaan ini.", "No documents in this build.")}</Card>}
          {doc && (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_220px]">
              <Card className="min-w-0 p-4 sm:p-6" data-docs-view>
                <button type="button" onClick={() => setListOpen(true)} className="mb-3 inline-flex items-center gap-1 text-xs text-muted underline decoration-dotted lg:hidden">
                  <ArrowLeft size={12} /> {t("Semua dokumen", "All documents")}
                </button>
                <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-3">
                  <p className="font-mono text-xs text-muted [overflow-wrap:anywhere]">{doc.path}</p>
                  <p className="flex items-center gap-2 text-[11px] text-muted" data-docs-changed>
                    {when && <span>{t("Diubah", "Changed")} {when}</span>}
                    {sizeText(doc.size) && <span>{sizeText(doc.size)}</span>}
                    <a href={GITHUB + doc.path.split("/").map(encodeURIComponent).join("/")} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 underline decoration-dotted">GitHub <ExternalLink size={11} /></a>
                  </p>
                </div>
                {err && <p className="mb-3 rounded-tile bg-danger/10 p-3 text-sm text-danger">{err}</p>}
                {tree == null && !err && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 size={14} className="animate-spin" /> {t("Membuka…", "Opening…")}</p>}
                {tree != null && outline.length > 2 && (
                  <details className="mb-4 rounded-tile bg-surface-2 p-3 text-xs xl:hidden">
                    <summary className="cursor-pointer font-medium">{t("Kandungan", "Contents")} ({outline.length})</summary>
                    <Outline items={outline} />
                  </details>
                )}
                {tree != null && <Markdown tree={tree} headingIds={outline.map((o) => o.id)} className="max-w-3xl text-sm" />}
              </Card>
              {outline.length > 0 && (
                <aside className="hidden xl:block">
                  <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-card border border-line/80 bg-surface p-3 text-xs" data-docs-outline>
                    <p className="mb-1 flex items-center gap-1 font-medium"><ListTree size={13} aria-hidden /> {t("Kandungan", "Contents")}</p>
                    <Outline items={outline} />
                  </div>
                </aside>
              )}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function Outline({ items }) {
  return (
    <ol className="mt-1 space-y-0.5">
      {items.map((o) => (
        <li key={o.id} style={{ paddingLeft: `${(o.level - 1) * 10}px` }}>
          {/* a button, not an <a href="#…">: the page's tabs live in the hash, so a heading anchor would change the page */}
          <button type="button" onClick={() => document.getElementById(o.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="block w-full truncate text-left text-muted hover:text-accent" title={o.text}>{o.text}</button>
        </li>
      ))}
    </ol>
  );
}

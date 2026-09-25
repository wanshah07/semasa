import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { fadeUp } from "./design/motion";
import { TABLES, configured } from "./lib/SupabaseClient";
import { brandOf } from "./lib/brand";
import { stampMYT } from "./lib/format";
import { useCanUpload, useGenerations, useSession, useSettings, useTable, useToasts, useTrends } from "./lib/hooks";
import FilterBar from "./components/FilterBar";
import Gate from "./components/Gate";
import IdeaComposer from "./components/IdeaComposer";
import PromptLibrary from "./components/PromptLibrary";
import IdeasTab from "./pages/IdeasTab";
import PostsTab from "./pages/PostsTab";
import SettingsTab from "./pages/SettingsTab";
import GenerationGallery from "./components/GenerationGallery";
import Header from "./components/Header";
import MasonryGrid from "./components/MasonryGrid";
import MediaUploader from "./components/MediaUploader";
import Toasts from "./components/Toast";
import Button from "./components/ui/Button";

function Unconfigured() {
  return (
    <main className="mx-auto max-w-page px-6 py-24 text-center">
      <h1 className="text-3xl">Semasa belum disambungkan</h1>
      <p className="mx-auto mt-3 max-w-lg text-sm text-muted">
        Tetapkan <code>VITE_SUPABASE_URL</code> dan <code>VITE_SUPABASE_ANON_KEY</code> sebagai repository variables,
        atau dalam <code>web/.env.local</code> untuk <code>npm run dev</code>.
      </p>
    </main>
  );
}

function IsuTab({ trends, onToast, onIdea }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [lang, setLang] = useState("");

  const counts = useMemo(() => {
    const c = { all: trends.rows.length };
    for (const r of trends.rows) c[r.category] = (c[r.category] || 0) + 1;
    return c;
  }, [trends.rows]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return trends.rows.filter((r) =>
      (!category || r.category === category) &&
      (!lang || r.lang === lang) &&
      (!q || [r.title, r.summary, r.source].some((t) => (t || "").toLowerCase().includes(q))));
  }, [trends.rows, query, category, lang]);

  const run = trends.lastRun;
  const failing = (run?.sources || []).filter((s) => !s.ok);

  return (
    <>
      <section className="hero-bg">
        <div className="mx-auto max-w-page px-4 pb-8 pt-12 sm:px-6 sm:pt-16">
          <motion.div variants={fadeUp} initial="hidden" animate="show">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Isu semasa Malaysia</p>
            <h1 className="mt-2 max-w-3xl text-4xl leading-[1.05] sm:text-5xl">Apa yang orang Malaysia baca dan cari, sekarang.</h1>
            <p className="mt-4 max-w-2xl text-sm text-muted sm:text-base">
              Dikutip setiap dua jam daripada portal berita utama, Google News dan Google Trends. Kategori dan ringkasan oleh AI;
              baris bertanda <span className="rounded-pill bg-accent/10 px-1.5 text-accent">AI</span> telah diringkaskan, yang lain mengikut peraturan kata kunci.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3 text-xs text-muted">
              {run ? (
                <>
                  <span>Larian terakhir {stampMYT(run.started_at)} · {run.inserted} baharu daripada {run.seen} dibaca</span>
                  <span className={`rounded-pill px-2 py-0.5 ${run.llm_ok ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"}`}>
                    LLM {run.llm_ok ? "aktif" : "tidak digunakan"}{run.llm_model ? ` · ${run.llm_model}` : ""}
                  </span>
                  {failing.length > 0 && (
                    <span className="rounded-pill bg-danger/10 px-2 py-0.5 text-danger" title={failing.map((s) => `${s.name}: ${s.error}`).join("\n")}>
                      {failing.length} sumber gagal
                    </span>
                  )}
                </>
              ) : <span>Belum ada larian direkodkan.</span>}
              <Button variant="ghost" size="sm" onClick={() => { trends.reload(); onToast("Dikemas kini.", "info"); }}>
                <RefreshCw size={12} /> Muat semula
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      <main className="mx-auto max-w-page px-4 pb-20 sm:px-6">
        <div className="sticky top-[62px] z-30 -mx-4 bg-bg/85 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
          <FilterBar query={query} setQuery={setQuery} category={category} setCategory={setCategory} lang={lang} setLang={setLang} counts={counts} />
        </div>
        {trends.error && <p className="my-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{trends.error}</p>}
        <div className="mt-4">
          <MasonryGrid rows={filtered} loading={trends.loading} onCategory={(c) => setCategory(c)} onIdea={onIdea} />
        </div>
      </main>
    </>
  );
}

function MediaTab({ user, gens, prompts, onToast }) {
  const [preset, setPreset] = useState(null);
  const clearPreset = useCallback(() => setPreset(null), []);
  async function guard(fn) {
    try { await fn(); } catch (e) { onToast(e.message, "danger"); }
  }
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Aliran B · makmal media</p>
        <h1 className="mt-2 text-4xl leading-tight">Prompt atau rujukan masuk, imej atau video keluar.</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          Tulis prompt sahaja, atau muat naik gambar rujukan: bot membacanya dahulu, kemudian mencipta semula mengikut
          arahan anda. Simpan prompt yang baik ke pustaka untuk diguna semula. GitHub Actions menjalankan penjanaan;
          status bertukar secara langsung.
        </p>
      </motion.div>
      <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_380px]">
        <MediaUploader user={user} onToast={onToast} onQueued={() => { gens.reload(); prompts.reload(); }}
          preset={preset} onPresetUsed={clearPreset} />
        <PromptLibrary prompts={prompts} onToast={onToast} onUse={(p) => { setPreset(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      </div>
      <h2 className="mb-4 mt-12 text-xl">Hasil</h2>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <GenerationGallery rows={gens.rows} user={user}
        onRequeue={(id) => guard(async () => { await gens.requeue(id); onToast("Dimasukkan semula ke giliran.", "ok"); })}
        onRemove={(row) => guard(async () => { if (window.confirm("Padam kerja ini?")) { await gens.remove(row); onToast("Dipadam.", "info"); } })} />
    </main>
  );
}

const TAB_IDS = ["isu", "idea", "post", "media", "tetapan"];

export default function App() {
  const [tab, setTab] = useState(() => {
    const h = window.location.hash.replace("#", "");
    return TAB_IDS.includes(h) ? h : "isu";
  });
  const [focusPost, setFocusPost] = useState(null);
  // follow the address bar too: Back/Forward and a pasted #post link switch the tab
  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.replace("#", "");
      setTab(TAB_IDS.includes(h) ? h : "isu");
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const [ideaFrom, setIdeaFrom] = useState(null);
  const { user, ready } = useSession();
  const canUpload = useCanUpload(user);
  const allowed = canUpload === true;
  const trends = useTrends();
  const { toasts, push } = useToasts();
  const gens = useGenerations({ enabled: allowed });
  const ideas = useTable(TABLES.ideas, { enabled: allowed });
  const posts = useTable(TABLES.posts, { enabled: allowed, limit: 400 });
  const prompts = useTable(TABLES.prompts, { enabled: allowed, realtime: false });
  const log = useTable(TABLES.publishLog, { enabled: allowed, order: "at", limit: 400, realtime: false });
  const { settings, save } = useSettings(allowed);
  const brand = useMemo(() => brandOf(settings), [settings]);

  function go(t) { setTab(t); window.location.hash = t === "isu" ? "" : t; }
  const gate = (node) => <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6"><Gate user={user} ready={ready} canUpload={canUpload} onToast={push}>{node}</Gate></main>;

  let body;
  if (!configured) body = <Unconfigured />;
  else if (tab === "idea") body = allowed ? <IdeasTab ideas={ideas} user={user} brand={brand} onToast={push}
    openPost={(id) => { setFocusPost(id); go("post"); }} /> : gate(null);
  else if (tab === "post") body = allowed ? <PostsTab posts={posts} media={gens} log={log} brand={brand} user={user}
    settings={settings} onToast={push} focusId={focusPost} setFocusId={setFocusPost} /> : gate(null);
  else if (tab === "media") body = allowed ? <MediaTab user={user} gens={gens} prompts={prompts} onToast={push} /> : gate(null);
  else if (tab === "tetapan") body = allowed ? <SettingsTab settings={settings} brand={brand} save={save} onToast={push} /> : gate(null);
  else body = <IsuTab trends={trends} onToast={push} onIdea={allowed ? setIdeaFrom : undefined} />;

  return (
    <div id="top" className="min-h-screen">
      <Header tab={tab} setTab={go} user={user} />
      {body}
      {allowed && (
        <IdeaComposer open={Boolean(ideaFrom)} onClose={() => setIdeaFrom(null)} trend={ideaFrom} user={user} brand={brand}
          onToast={push} onDone={() => ideas.reload()} />
      )}
      <footer className="border-t border-line py-8 text-center text-[11px] text-muted">
        Semasa · sumber berita kekal milik penerbit masing-masing · dikemas kini setiap 2 jam
      </footer>
      <Toasts toasts={toasts} />
    </div>
  );
}

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { fadeUp } from "./design/motion";
import { configured } from "./lib/SupabaseClient";
import { stampMYT } from "./lib/format";
import { useCanUpload, useGenerations, useSession, useToasts, useTrends } from "./lib/hooks";
import AuthPanel from "./components/AuthPanel";
import FilterBar from "./components/FilterBar";
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

function IsuTab({ trends, onToast }) {
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
          <MasonryGrid rows={filtered} loading={trends.loading} onCategory={(c) => setCategory(c)} />
        </div>
      </main>
    </>
  );
}

function NotListed({ user }) {
  return (
    <div className="mx-auto max-w-md rounded-card border border-line bg-surface p-6 shadow-card">
      <h3 className="text-lg">Akaun ini belum dibenarkan memuat naik</h3>
      <p className="mt-2 text-sm text-muted">
        {user.email} sudah log masuk, tetapi tiada dalam senarai <code>semasa_uploaders</code>. Pemilik projek
        perlu menambah akaun ini dalam Supabase SQL editor sebelum kerja penjanaan boleh dihantar.
      </p>
    </div>
  );
}

function MediaTab({ user, ready, onToast }) {
  const gens = useGenerations();
  const canUpload = useCanUpload(user);
  async function guard(fn) {
    try { await fn(); } catch (e) { onToast(e.message, "danger"); }
  }
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Makmal media</p>
        <h1 className="mt-2 text-4xl leading-tight">Rujukan masuk, imej atau video keluar.</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          Fail disimpan di Supabase Storage; GitHub Actions menjalankan penjanaan dan menulis alamat hasil semula ke sini.
          Status bertukar secara langsung.
        </p>
      </motion.div>
      <div className="mt-8">
        {!ready ? null : !user
          ? <AuthPanel onToast={onToast} />
          : canUpload === null ? null
          : canUpload
            ? <MediaUploader user={user} onToast={onToast} onQueued={() => gens.reload()} />
            : <NotListed user={user} />}
      </div>
      <h2 className="mb-4 mt-12 text-xl">Hasil</h2>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <GenerationGallery rows={gens.rows} user={user}
        onRequeue={(id) => guard(async () => { await gens.requeue(id); onToast("Dimasukkan semula ke giliran.", "ok"); })}
        onRemove={(row) => guard(async () => { if (window.confirm("Padam kerja ini?")) { await gens.remove(row); onToast("Dipadam.", "info"); } })} />
    </main>
  );
}

export default function App() {
  const [tab, setTab] = useState(() => (window.location.hash === "#media" ? "media" : "isu"));
  const { user, ready } = useSession();
  const trends = useTrends();
  const { toasts, push } = useToasts();

  function go(t) { setTab(t); window.location.hash = t === "media" ? "media" : ""; }

  return (
    <div id="top" className="min-h-screen">
      <Header tab={tab} setTab={go} user={user} />
      {!configured ? <Unconfigured /> : tab === "media"
        ? <MediaTab user={user} ready={ready} onToast={push} />
        : <IsuTab trends={trends} onToast={push} />}
      <footer className="border-t border-line py-8 text-center text-[11px] text-muted">
        Semasa · sumber berita kekal milik penerbit masing-masing · dikemas kini setiap 2 jam
      </footer>
      <Toasts toasts={toasts} />
    </div>
  );
}

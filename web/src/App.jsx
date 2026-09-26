import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { fadeUp } from "./design/motion";
import { TABLES, configured, errText, supabase } from "./lib/SupabaseClient";
import { FAQ_CATEGORY_TO_DOMAIN, FAQ_SOURCE, brandOf } from "./lib/brand";
import { stampMYT } from "./lib/format";
import { currentLang, useLang } from "./lib/i18n";
import { useCanUpload, useGenerations, useSession, useSettings, useTable, useToasts, useTrends } from "./lib/hooks";
import FilterBar from "./components/FilterBar";
import Gate from "./components/Gate";
import IdeaComposer from "./components/IdeaComposer";
import PromptLibrary from "./components/PromptLibrary";
import DesignTab from "./pages/DesignTab";
import FaqTab from "./pages/FaqTab";
import LogTab from "./pages/LogTab";
import IdeasTab from "./pages/IdeasTab";
import PostsTab from "./pages/PostsTab";
import SettingsTab from "./pages/SettingsTab";
import GenerationGallery from "./components/GenerationGallery";
import VideoTab from "./pages/VideoTab";
import WatchSegment, { watchIdea } from "./components/WatchSegment";
import Header from "./components/Header";
import MasonryGrid from "./components/MasonryGrid";
import TrendTable from "./components/TrendTable";
import ViewToggle, { useView } from "./components/ViewToggle";
import MediaUploader from "./components/MediaUploader";
import Toasts from "./components/Toast";
import Button from "./components/ui/Button";

function Unconfigured() {
  const { t, lang } = useLang();
  return (
    <main className="mx-auto max-w-page px-6 py-24 text-center">
      <h1 className="text-3xl">{t("Semasa belum disambungkan", "Semasa is not connected yet")}</h1>
      <p className="mx-auto mt-3 max-w-lg text-sm text-muted">
        {lang === "en" ? (
          <>
            Set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code> as repository variables,
            or in <code>web/.env.local</code> for <code>npm run dev</code>.
          </>
        ) : (
          <>
            Tetapkan <code>VITE_SUPABASE_URL</code> dan <code>VITE_SUPABASE_ANON_KEY</code> sebagai repository variables,
            atau dalam <code>web/.env.local</code> untuk <code>npm run dev</code>.
          </>
        )}
      </p>
    </main>
  );
}

const SEGMENTS = ["isu", "regulatory", "publication"];

function IsuTab({ trends, onToast, onIdea, onFaq, allowed, gateNode, settings, save, brand }) {
  const { t } = useLang();
  const [segRaw, setSeg] = useView("isu.segment", "isu");
  const seg = SEGMENTS.includes(segRaw) ? segRaw : "isu";
  // the two watch segments share one list; it is read only while one of them is open
  const watch = useTable(TABLES.watch, { enabled: allowed && seg !== "isu", limit: 600, realtime: false, everyMs: 120_000 });
  const segTabs = (
    <div role="tablist" aria-label={t("Segmen", "Segments")} className="mb-5 flex flex-wrap gap-1.5">
      {[["isu", t("Isu semasa", "Current issues")], ["regulatory", t("Regulatori", "Regulatory")],
        ["publication", t("Penerbitan terkini", "Latest publications")]].map(([v, l]) => (
        <button type="button" key={v} role="tab" aria-selected={seg === v} onClick={() => setSeg(v)}
          className={`rounded-pill px-4 py-2 text-sm font-medium ${seg === v ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>{l}</button>
      ))}
    </div>
  );
  if (seg !== "isu") {
    const reg = seg === "regulatory";
    return (
      <>
        <section className="hero-bg">
          <div className="mx-auto max-w-page px-4 pb-8 pt-12 sm:px-6 sm:pt-16">
            <motion.div variants={fadeUp} initial="hidden" animate="show">
              {segTabs}
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
                {reg ? t("Regulatori", "Regulatory") : t("Penerbitan terkini", "Latest publications")}</p>
              <h1 className="mt-2 max-w-3xl text-4xl leading-[1.05] sm:text-5xl">
                {reg ? t("Apa yang pengawal selia umumkan, terus dari sumbernya.", "What the regulators announce, straight from the source.")
                  : t("Kajian terbaharu tentang kosmetik, kulit dan halal.", "The newest research on cosmetics, skin and halal.")}
              </h1>
              <p className="mt-4 max-w-2xl text-sm text-muted sm:text-base">
                {reg
                  ? t("Disapu sekali sehari daripada halaman NPRA, Portal Halal Malaysia, HSA Singapura, SCCS EU, OPSS UK dan NMPA China sendiri. AI meringkaskan setiap notis dalam BM, memilih domain dan menulis kenapa ia penting.",
                    "Swept once a day from the own pages of NPRA, Portal Halal Malaysia, HSA Singapore, EU SCCS, UK OPSS and China NMPA. AI summarises each notice in Malay, picks its domain and says why it matters.")
                  : t("Disapu sekali sehari daripada PubMed: kertas 14 hari terakhir tentang sains kosmetik, dermatologi pengguna, sains halal dan bahan cemar kosmetik. Pengarang, jurnal dan DOI ikut sekali ke idea.",
                    "Swept once a day from PubMed: papers from the last 14 days on cosmetic science, consumer dermatology, halal science and cosmetic contaminants. Authors, journal and DOI travel with the idea.")}
              </p>
            </motion.div>
          </div>
        </section>
        {allowed ? (
          <main className="mx-auto max-w-page px-4 pb-20 sm:px-6">
            <WatchSegment section={seg} watch={watch} setting={settings.watch} saveSetting={save} brand={brand}
              onIdea={onIdea ? (r) => onIdea(watchIdea(r, brand)) : undefined} onToast={onToast} />
          </main>
        ) : gateNode}
      </>
    );
  }
  return <IsuHeadlines trends={trends} onToast={onToast} onIdea={onIdea} onFaq={onFaq} segTabs={segTabs} />;
}

function IsuHeadlines({ trends, onToast, onIdea, onFaq, segTabs }) {
  const { t } = useLang();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [lang, setLang] = useState("");
  const [view, setView] = useView("isu");

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
      (!q || [r.title, r.summary, r.source].some((v) => (v || "").toLowerCase().includes(q))));
  }, [trends.rows, query, category, lang]);

  const run = trends.lastRun;
  const failing = (run?.sources || []).filter((s) => !s.ok);

  return (
    <>
      <section className="hero-bg">
        <div className="mx-auto max-w-page px-4 pb-8 pt-12 sm:px-6 sm:pt-16">
          <motion.div variants={fadeUp} initial="hidden" animate="show">
            {segTabs}
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Isu semasa Malaysia", "Current issues in Malaysia")}</p>
            <h1 className="mt-2 max-w-3xl text-4xl leading-[1.05] sm:text-5xl">
              {t("Apa yang orang Malaysia baca dan cari, sekarang.", "What Malaysians are reading and searching for, right now.")}
            </h1>
            <p className="mt-4 max-w-2xl text-sm text-muted sm:text-base">
              {t("Dikutip setiap 8 jam daripada portal berita utama, Google News dan Google Trends. Kategori dan ringkasan oleh AI;",
                "Collected every 8 hours from the main news portals, Google News and Google Trends. Categories and summaries by AI;")}{" "}
              {t("baris bertanda", "rows marked")} <span className="rounded-pill bg-accent/10 px-1.5 text-accent">AI</span>{" "}
              {t("telah diringkaskan, yang lain mengikut peraturan kata kunci.", "were summarised by it, the rest follow keyword rules.")}
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3 text-xs text-muted">
              {run ? (
                <>
                  <span>{t("Larian terakhir {at} · {n} baharu daripada {m} dibaca", "Last run {at} · {n} new out of {m} read",
                    { at: stampMYT(run.started_at), n: run.inserted, m: run.seen })}</span>
                  <span className={`rounded-pill px-2 py-0.5 ${run.llm_ok ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"}`}>
                    LLM {run.llm_ok ? t("aktif", "active") : t("tidak digunakan", "not used")}{run.llm_model ? ` · ${run.llm_model}` : ""}
                  </span>
                  {failing.length > 0 && (
                    <span className="rounded-pill bg-danger/10 px-2 py-0.5 text-danger" title={failing.map((s) => `${s.name}: ${s.error}`).join("\n")}>
                      {t("{n} sumber gagal", ["{n} source failed", "{n} sources failed"], { n: failing.length })}
                    </span>
                  )}
                </>
              ) : <span>{t("Belum ada larian direkodkan.", "No run recorded yet.")}</span>}
              <Button variant="ghost" size="sm" onClick={() => { trends.reload(); onToast(t("Dikemas kini.", "Updated."), "info"); }}>
                <RefreshCw size={12} /> {t("Muat semula", "Reload")}
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      <main className="mx-auto max-w-page px-4 pb-20 sm:px-6">
        <div className="z-30 sm:sticky sm:top-[97px] xl:top-[65px] -mx-4 bg-bg/85 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
          <FilterBar query={query} setQuery={setQuery} category={category} setCategory={setCategory} lang={lang} setLang={setLang} counts={counts} />
        </div>
        {trends.error && <p className="my-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{trends.error}</p>}
        <div className="mt-4 flex justify-end"><ViewToggle view={view} setView={setView} /></div>
        <div className="mt-3">
          {view === "table"
            ? <TrendTable rows={filtered} loading={trends.loading} onCategory={(c) => setCategory(c)} onIdea={onIdea} onFaq={onFaq} />
            : <MasonryGrid rows={filtered} loading={trends.loading} onCategory={(c) => setCategory(c)} onIdea={onIdea} onFaq={onFaq} />}
        </div>
      </main>
    </>
  );
}

function MediaTab({ user, gens, prompts, onToast }) {
  const { t } = useLang();
  const [preset, setPreset] = useState(null);
  const clearPreset = useCallback(() => setPreset(null), []);
  async function guard(fn) {
    try { await fn(); } catch (e) { onToast(e.message, "danger"); }
  }
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Aliran B · makmal media", "Flow B · media lab")}</p>
        <h1 className="mt-2 text-4xl leading-tight">
          {t("Prompt atau rujukan masuk, imej atau video keluar.", "A prompt or a reference goes in, an image or a video comes out.")}
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Tulis prompt sahaja, atau muat naik gambar rujukan: bot membacanya dahulu, kemudian mencipta semula mengikut "
            + "arahan anda. Simpan prompt yang baik ke pustaka untuk diguna semula. GitHub Actions menjalankan penjanaan; "
            + "status bertukar secara langsung.",
          "Write a prompt on its own, or upload a reference picture: the bot reads it first, then recreates it following "
            + "your instructions. Save a good prompt to the library to use it again. GitHub Actions runs the generation; "
            + "the status updates live.")}
        </p>
      </motion.div>
      <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_380px]">
        <MediaUploader user={user} onToast={onToast} onQueued={() => { gens.reload(); prompts.reload(); }}
          preset={preset} onPresetUsed={clearPreset} />
        <PromptLibrary prompts={prompts} onToast={onToast} onUse={(p) => { setPreset(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      </div>
      <p className="mt-3 text-[11px] text-muted">{t("Mahu foto sebenar? Pilih Unsplash dalam menu penyedia: foto yang dipilih jadi gambar biasa (gambar post, latar slaid atau latar reka bentuk), dan jurugambar dikreditkan.",
        "Want a real photo? Choose Unsplash in the provider menu: the chosen photo becomes an ordinary picture (a post picture, a slide background or a design background), and the photographer is credited.")}</p>
      <h2 className="mb-4 mt-12 text-xl">{t("Hasil", "Results")}</h2>
      {gens.error && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{gens.error}</p>}
      <GenerationGallery rows={gens.rows} user={user} onToast={onToast}
        onRequeue={(id, provider) => guard(async () => { await gens.requeue(id, provider); onToast(t("Dimasukkan semula ke giliran.", "Put back in the queue."), "ok"); })}
        onRemove={(row) => guard(async () => { if (window.confirm(t("Padam kerja ini?", "Delete this job?"))) {
          await gens.remove(row); onToast(t("Dipadam.", "Deleted."), "info");
        } })} />
    </main>
  );
}

const TAB_IDS = ["isu", "idea", "post", "media", "design", "video", "faq", "log", "tetapan"];

export default function App() {
  const { t } = useLang();                                   // read here so a language switch re-renders the page
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
  // the two big lists stream live changes only while their tab is open; elsewhere a slow poll is enough
  const faqs = useTable(TABLES.faqs, { enabled: allowed, limit: 3000, realtime: tab === "faq" });
  const activity = useTable(TABLES.log, { enabled: allowed && tab === "log", order: "at", limit: 3000 });

  // "Jadikan FAQ" on a headline: the worker reads the article and writes one bilingual FAQ from it
  async function faqFrom(trend) {
    const { error } = await supabase.from(TABLES.faqs).insert({
      status: "new", source_kind: "headline", trend_id: trend.id, source_url: trend.url, source_name: trend.source,
      raw_question: trend.title, raw_answer: trend.summary || "", created_by: user.id,
    });
    if (error) {
      return push(/semasa_faqs/.test(errText(error))
        ? t("FAQ belum disediakan: jalankan supabase/007_faq.sql sekali.", "FAQ is not set up yet: run supabase/007_faq.sql once.")
        : errText(error), "danger");
    }
    push(t("Dihantar. AI akan baca artikel dan tulis satu FAQ; lihat tab FAQ.",
      "Sent. The AI will read the article and write one FAQ; see the FAQ tab."), "ok");
    faqs.reload();
  }
  // "Jadikan post" on an FAQ: the question is the headline and the answer is the source the writer works from
  function faqIdea(r) {
    const bm = currentLang() !== "en";
    const q = (bm ? r.question_bm : r.question_en) || r.question_bm || r.question_en || r.raw_question || "";
    const a = (bm ? r.answer_bm : r.answer_en) || r.answer_bm || r.answer_en || "";
    const unchecked = r.needs_check || r.answer_source === "ai";
    return {
      faq: true, id: r.id, title: q, url: null, source: FAQ_SOURCE, category: r.category,
      domain: FAQ_CATEGORY_TO_DOMAIN[r.category] || "",
      summary: [a, r.instrument ? `Sumber: ${r.instrument}` : "",
        unchecked ? "(Jawapan ini ditulis AI dan belum disemak: setiap fakta khusus perlu [SAHKAN].)" : ""].filter(Boolean).join("\n\n"),
    };
  }
  const { settings, save } = useSettings(allowed);
  const brand = useMemo(() => brandOf(settings), [settings]);

  function go(next) { setTab(next); window.location.hash = next === "isu" ? "" : next; }
  const gate = (node) => <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6"><Gate user={user} ready={ready} canUpload={canUpload} onToast={push}>{node}</Gate></main>;

  let body;
  if (!configured) body = <Unconfigured />;
  else if (tab === "idea") body = allowed ? <IdeasTab ideas={ideas} user={user} brand={brand} onToast={push}
    openPost={(id) => { setFocusPost(id); go("post"); }} /> : gate(null);
  else if (tab === "post") body = allowed ? <PostsTab posts={posts} media={gens} log={log} brand={brand} user={user}
    settings={settings} onToast={push} focusId={focusPost} setFocusId={setFocusPost} /> : gate(null);
  else if (tab === "media") body = allowed ? <MediaTab user={user} gens={gens} prompts={prompts} onToast={push} /> : gate(null);
  else if (tab === "design") body = allowed ? <DesignTab user={user} gens={gens} posts={posts} brand={brand} onToast={push} /> : gate(null);
  else if (tab === "video") body = allowed ? <VideoTab user={user} gens={gens} brand={brand} onToast={push}
    openPost={(id) => { setFocusPost(id); go("post"); }} /> : gate(null);
  else if (tab === "faq") body = allowed ? <FaqTab faqs={faqs} settings={settings} brand={brand} user={user} onToast={push}
    onPost={(r) => setIdeaFrom(faqIdea(r))} /> : gate(null);
  else if (tab === "log") body = allowed ? <LogTab log={activity} onOpen={(to) => { if (to.postId) setFocusPost(to.postId); go(to.tab); }} /> : gate(null);
  else if (tab === "tetapan") body = allowed ? <SettingsTab settings={settings} brand={brand} save={save} onToast={push} /> : gate(null);
  else body = <IsuTab trends={trends} onToast={push} onIdea={allowed ? setIdeaFrom : undefined} onFaq={allowed ? faqFrom : undefined}
    allowed={allowed} gateNode={allowed ? null : gate(null)} settings={settings} save={save} brand={brand} />;

  return (
    <div id="top" className="min-h-screen">
      <Header tab={tab} setTab={go} user={user} />
      {body}
      {allowed && (
        <IdeaComposer open={Boolean(ideaFrom)} onClose={() => setIdeaFrom(null)} trend={ideaFrom} user={user} brand={brand}
          onToast={push} onDone={() => ideas.reload()} />
      )}
      <footer className="border-t border-line py-8 text-center text-[11px] text-muted">
        {t("Semasa · sumber berita kekal milik penerbit masing-masing · dikemas kini setiap 8 jam · "
          + "isu yang tidak dijadikan idea hilang selepas 48 jam",
        "Semasa · news sources remain the property of their publishers · updated every 8 hours · "
          + "issues not turned into an idea disappear after 48 hours")}
      </footer>
      <Toasts toasts={toasts} />
    </div>
  );
}

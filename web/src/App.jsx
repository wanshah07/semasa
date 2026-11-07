import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
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
import { DesignsContext } from "./lib/designsContext";
import { watchIdea } from "./lib/watchIdea";
import Header from "./components/Header";
import AppSidebar from "./components/AppSidebar";
import SegmentBar from "./components/SegmentBar";
import ViewToggle, { useView } from "./components/ViewToggle";
import Toasts from "./components/Toast";
import Button from "./components/ui/Button";
import Guide from "./components/Guide";
import MobileTabBar from "./components/MobileTabBar";
import InstallHint from "./components/InstallHint";
/* Every tab and every heavy panel is loaded when it is first shown, not with the page. The first screen is the sign-in card
   (or the headlines), and on a phone on a slow connection it used to wait for one 768 KB script carrying every tab, the card
   renderer, the motion rules and the office writers. Only Gate, Header, the sidebar and the hooks stay in the first chunk. */
const IdeaComposer = lazy(() => import("./components/IdeaComposer"));
const PromptLibrary = lazy(() => import("./components/PromptLibrary"));
const MediaUploader = lazy(() => import("./components/MediaUploader"));
const WatchSegment = lazy(() => import("./components/WatchSegment"));
const MasonryGrid = lazy(() => import("./components/MasonryGrid"));
const TrendTable = lazy(() => import("./components/TrendTable"));
const DesignTab = lazy(() => import("./pages/DesignTab"));
const FaqTab = lazy(() => import("./pages/FaqTab"));
const FragranceTab = lazy(() => import("./pages/FragranceTab"));
const LogTab = lazy(() => import("./pages/LogTab"));
const IdeasTab = lazy(() => import("./pages/IdeasTab"));
const PostsTab = lazy(() => import("./pages/PostsTab"));
const SettingsTab = lazy(() => import("./pages/SettingsTab"));
const VideoTab = lazy(() => import("./pages/VideoTab"));
const ImageLibraryTab = lazy(() => import("./pages/ImageLibraryTab"));
const VideoLibraryTab = lazy(() => import("./pages/VideoLibraryTab"));
const MotionSkillsTab = lazy(() => import("./pages/MotionSkillsTab"));
const ChatTab = lazy(() => import("./pages/ChatTab"));
const BillingTab = lazy(() => import("./pages/BillingTab"));
const BillingPublic = lazy(() => import("./pages/BillingPublic"));
const HomeTab = lazy(() => import("./pages/HomeTab"));
const SubscriptionsTab = lazy(() => import("./pages/SubscriptionsTab"));
const CrmTab = lazy(() => import("./pages/CrmTab"));
const CrmUnsubscribe = lazy(() => import("./pages/CrmUnsubscribe"));
const ResitTab = lazy(() => import("./pages/ResitTab"));
const BrainTab = lazy(() => import("./pages/BrainTab"));
const PrestasiTab = lazy(() => import("./pages/PrestasiTab"));
const RepoTab = lazy(() => import("./pages/RepoTab"));
const OfficeTab = lazy(() => import("./pages/OfficeTab"));
const MoneyTab = lazy(() => import("./pages/MoneyTab"));
const TechOverviewTab = lazy(() => import("./pages/TechOverviewTab"));
const BusinessesTab = lazy(() => import("./pages/BusinessesTab"));
const HooksTab = lazy(() => import("./pages/HooksTab"));
const WritingStylesTab = lazy(() => import("./pages/WritingStylesTab"));
const StackTab = lazy(() => import("./pages/StackTab"));
const ApiTab = lazy(() => import("./pages/ApiTab"));
const MemoryTab = lazy(() => import("./pages/MemoryTab"));
const DocsTab = lazy(() => import("./pages/DocsTab"));
import { setWanshah } from "./lib/cards/library";
import { approvedPoses } from "./lib/wanshah";

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

/** What stands in a tab's place while its code arrives (a moment on wifi, a second or two on a slow phone). */
const Waiting = () => <main className="grid min-h-[40vh] place-items-center text-sm text-muted" aria-busy="true">…</main>;

const SEGMENTS = ["isu", "regulatory", "publication", "reddit", "youtube", "folder", "myra"];

/* The words above each segment that is not the news headlines. Reddit, YouTube, OneDrive and MYRA are Wan's own sources
   (supabase/024, backend/semasa/intake.py): each is a tab here, over the same semasa_watch rows. */
function segCopy(seg, t) {
  const copy = {
    regulatory: [t("Regulatori", "Regulatory"), t("Apa yang pengawal selia umumkan, terus dari sumbernya.", "What the regulators announce, straight from the source."),
      t("Disapu sekali sehari daripada halaman NPRA, Portal Halal Malaysia, HSA Singapura, SCCS EU, OPSS UK dan NMPA China sendiri. AI meringkaskan setiap notis dalam BM, memilih domain dan menulis kenapa ia penting.",
        "Swept once a day from the own pages of NPRA, Portal Halal Malaysia, HSA Singapore, EU SCCS, UK OPSS and China NMPA. AI summarises each notice in Malay, picks its domain and says why it matters.")],
    publication: [t("Penerbitan terkini", "Latest publications"), t("Kajian terbaharu tentang kosmetik, kulit dan halal.", "The newest research on cosmetics, skin and halal."),
      t("Disapu sekali sehari daripada PubMed: kertas 14 hari terakhir tentang sains kosmetik, dermatologi pengguna, sains halal dan bahan cemar kosmetik. Pengarang, jurnal dan DOI ikut sekali ke idea.",
        "Swept once a day from PubMed: papers from the last 14 days on cosmetic science, consumer dermatology, halal science and cosmetic contaminants. Authors, journal and DOI travel with the idea.")],
    reddit: ["Reddit", t("Apa yang orang Malaysia sedang bertengkar, minggu ini.", "What Malaysians are arguing about this week."),
      t("Benang r/malaysia paling banyak komen tentang halal, kosmetik, krim sunscreen, suplemen dan label. Setiap baris ialah kepercayaan yang perlu dibetulkan, ditulis semula secara neutral: platform dan pautannya tidak masuk ke dalam post.",
        "The most-commented r/malaysia threads on halal, cosmetics, sunscreen, supplements and labels. Each row is the belief to correct, rewritten neutrally: the platform and its link never reach a post.")],
    youtube: ["YouTube", t("Video yang sedang ditonton dan dipertikaikan.", "The videos people are watching and disputing."),
      t("Video paling ditonton dalam 14 hari terakhir tentang kulit, sunscreen dan halal di Malaysia. Bilangan tontonan ialah angka sebenar daripada YouTube. Kuota carian YouTube dikongsi dan kadang-kadang habis; kalau begitu Reddit tetap berjalan.",
        "The most-watched videos of the last 14 days on skin, sunscreen and halal in Malaysia. View counts are YouTube's own. The search quota is shared and sometimes runs out; Reddit carries on when it does.")],
    folder: ["OneDrive", t("Sudut siaran daripada perpustakaan rujukan anda.", "Post angles from your own reference library."),
      t("Setiap fail dalam /40. HERMES dibaca sekali: sehingga 8 sudut, tiada nama pelanggan atau nombor fail. Matriks siaran LabMuffin masuk baris demi baris. Folder “urgent post/DDMMYY” untuk hari ini atau esok didahulukan.",
        "Each file in /40. HERMES is read once: up to 8 angles, no client names or file numbers. The LabMuffin post matrix comes in row by row. An “urgent post/DDMMYY” folder for today or tomorrow goes first.")],
    myra: ["MYRA", t("Penemuan harian daripada Daftar Peraturan Kosmetik Global.", "Daily findings from the Global Cosmetic Reg Daily Log."),
      t("Dibaca terus daripada lembaran MYRA (baca sahaja). Hanya baris “Ada Update? = Yes”; setiap penemuan dalam Ringkasan ialah satu baris. Kalau satu pautan dikongsi beberapa penemuan, ia ditandakan.",
        "Read straight from MYRA's sheet (read only). Only rows with “Ada Update? = Yes”; each finding in the Ringkasan is one row. A link shared by several findings is flagged.")],
  };
  return copy[seg] || copy.publication;
}

function IsuTab({ trends, onToast, onIdea, onFaq, allowed, gateNode, settings, save, brand, user }) {
  const { t } = useLang();
  const [segRaw, setSeg] = useView("isu.segment", "isu");
  const seg = SEGMENTS.includes(segRaw) ? segRaw : "isu";
  // the two watch segments share one list; it is read only while one of them is open
  const watch = useTable(TABLES.watch, { enabled: allowed && seg !== "isu", limit: 900, realtime: false, everyMs: 120_000 });
  const segTabs = (
    <div role="tablist" aria-label={t("Segmen", "Segments")} className="mb-5 flex flex-wrap gap-1.5">
      {[["isu", t("Isu semasa", "Current issues")], ["regulatory", t("Regulatori", "Regulatory")],
        ["publication", t("Penerbitan terkini", "Latest publications")], ["reddit", "Reddit"], ["youtube", "YouTube"],
        ["folder", "OneDrive"], ["myra", "MYRA"]].map(([v, l]) => (
        <button type="button" key={v} role="tab" aria-selected={seg === v} onClick={() => setSeg(v)}
          className={`rounded-pill px-4 py-2 text-sm font-medium ${seg === v ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>{l}</button>
      ))}
    </div>
  );
  if (seg !== "isu") {
    const [eyebrow, headline, blurb] = segCopy(seg, t);
    return (
      <>
        <section className="hero-bg">
          <div className="mx-auto max-w-page px-4 pb-8 pt-12 sm:px-6 sm:pt-16">
            <motion.div variants={fadeUp} initial="hidden" animate="show">
              {segTabs}
              <p className="text-[13px] font-semibold text-accent">{eyebrow}</p>
              <h1 className="mt-2 max-w-3xl text-4xl leading-[1.05] sm:text-5xl">{headline}</h1>
              <p className="mt-4 max-w-2xl text-sm text-muted sm:text-base">{blurb}</p>
            </motion.div>
          </div>
        </section>
        {allowed ? (
          <main className="mx-auto max-w-page px-4 pb-20 sm:px-6">
            <Suspense fallback={<Waiting />}>
              <WatchSegment section={seg} watch={watch} setting={["reddit", "youtube", "folder", "myra"].includes(seg) ? settings.sources : settings.watch} saveSetting={save} brand={brand} user={user}
                onIdea={onIdea ? (r) => onIdea(watchIdea(r, brand)) : undefined} onToast={onToast} />
            </Suspense>
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
            <p className="text-[13px] font-semibold text-accent">{t("Isu semasa Malaysia", "Current issues in Malaysia")}</p>
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
          <Suspense fallback={<Waiting />}>
            {view === "table"
              ? <TrendTable rows={filtered} loading={trends.loading} onCategory={(c) => setCategory(c)} onIdea={onIdea} onFaq={onFaq} />
              : <MasonryGrid rows={filtered} loading={trends.loading} onCategory={(c) => setCategory(c)} onIdea={onIdea} onFaq={onFaq} />}
          </Suspense>
        </div>
      </main>
    </>
  );
}

/* Generate image (Wan, 11 Oct 2026: image and video apart, each with a library). The form and the prompt library only; what
   it makes is in the Image library page, and a video is made on Generate video. */
function MediaTab({ user, gens, prompts, onToast, go }) {
  const { t } = useLang();
  const [preset, setPreset] = useState(null);
  const clearPreset = useCallback(() => setPreset(null), []);
  const running = gens.rows.filter((r) => r.mode !== "fragrance" && r.type !== "video" && !r.meta?.design && ["pending", "processing"].includes(r.status)).length;
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-[13px] font-semibold text-accent">{t("Imej", "Image")}</p>
        <h1 className="mt-2 text-4xl leading-tight">
          {t("Prompt atau rujukan masuk, imej keluar.", "A prompt or a reference goes in, an image comes out.")}
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Tulis prompt sahaja, atau muat naik gambar rujukan: Semasa membacanya dahulu, kemudian mencipta semula mengikut "
            + "arahan anda. Simpan prompt yang baik ke pustaka untuk diguna semula. GitHub Actions menjalankan penjanaan; "
            + "status bertukar secara langsung.",
          "Write a prompt on its own, or upload a reference picture: Semasa reads it first, then recreates it following "
            + "your instructions. Save a good prompt to the library to use it again. GitHub Actions runs the generation; "
            + "the status updates live.")}
        </p>
        <p className="mt-2 text-sm text-muted">{t("Hasil ada di", "Results are in")}{" "}
          <button type="button" className="text-accent underline" onClick={() => go("media-lib")}>{t("Pustaka imej", "the Image library")}</button>
          {running > 0 ? ` · ${t("{n} sedang dijana", "{n} generating", { n: running })}` : ""}</p>
      </motion.div>
      <div className="mt-8 grid gap-5 lg:grid-cols-[1fr_380px]">
        <MediaUploader user={user} onToast={onToast} only="image" onQueued={() => { gens.reload(); prompts.reload(); }}
          preset={preset} onPresetUsed={clearPreset} />
        <PromptLibrary prompts={prompts} type="image" onToast={onToast} onUse={(p) => { setPreset(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      </div>
      <p className="mt-3 text-[11px] text-muted">{t("Mahu foto sebenar? Pilih Unsplash dalam menu penyedia: foto yang dipilih jadi gambar biasa (gambar post, latar slaid atau latar reka bentuk), dan jurugambar dikreditkan.",
        "Want a real photo? Choose Unsplash in the provider menu: the chosen photo becomes an ordinary picture (a post picture, a slide background or a design background), and the photographer is credited.")}</p>
    </main>
  );
}

const TAB_IDS = ["papan", "isu", "idea", "post", "hooks", "gaya", "prestasi", "media", "media-lib", "design", "design-lib", "wangian", "bil-valorith", "video", "video-lib", "motion-skills", "chat", "memori", "otak", "wang", "bil", "langganan", "crm", "syarikat", "resit", "faq", "log", "dokumen", "tech", "office", "repo", "api", "stack", "tetapan"];
// #bil/<token>: a client opening the "view online" link of a quotation, invoice or receipt (no sign-in; supabase/028 semasa_billing_public)
const PUBLIC_DOC = /^bil\/([a-f0-9]{32})$/;
// #crm/unsub/<token>: the unsubscribe link under every marketing e-mail (no sign-in; supabase/031 semasa_crm_unsubscribe)
const UNSUB = /^crm\/unsub\/([a-f0-9]{32})$/;


export default function App() {
  const { t } = useLang();                                   // read here so a language switch re-renders the page
  const [tab, setTab] = useState(() => {
    const h = window.location.hash.replace("#", "");
    return TAB_IDS.includes(h) ? h : "papan";                 // the home is the dashboard (Wan, 9 Oct 2026); #isu still opens the issues
  });
  const [pubToken, setPubToken] = useState(() => (PUBLIC_DOC.exec(window.location.hash.replace("#", "")) || [])[1] || "");
  const [unsubToken, setUnsubToken] = useState(() => (UNSUB.exec(window.location.hash.replace("#", "")) || [])[1] || "");
  const [focusPost, setFocusPost] = useState(null);
  // follow the address bar too: Back/Forward and a pasted #post link switch the tab
  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.replace("#", "");
      setPubToken((PUBLIC_DOC.exec(h) || [])[1] || "");
      setUnsubToken((UNSUB.exec(h) || [])[1] || "");
      const next = TAB_IDS.includes(h) ? h : "papan";
      setTab(next);
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
  // ws.regulab Studio's history came over on 27 Sep 2026 (supabase/020): a short list would drop the oldest rows unseen
  const posts = useTable(TABLES.posts, { enabled: allowed, limit: 1000 });
  // every picture a post points at, so an old post's pictures load even when 300 newer jobs exist
  const needMedia = useMemo(() => [...new Set(posts.rows.flatMap((p) => p.media_ids || []))].sort().join(","), [posts.rows]);
  const gens = useGenerations({ enabled: allowed, need: needMedia });
  const ideas = useTable(TABLES.ideas, { enabled: allowed, limit: 1000 });
  const prompts = useTable(TABLES.prompts, { enabled: allowed, realtime: false });
  const log = useTable(TABLES.publishLog, { enabled: allowed, order: "at", limit: 400, realtime: false });
  // the two big lists stream live changes only while their tab is open; elsewhere a slow poll is enough
  const faqs = useTable(TABLES.faqs, { enabled: allowed, limit: 3000, realtime: tab === "faq" });
  // the home dashboard shows the last few lines, so it loads the log too (a shorter read than the Log tab's)
  const activity = useTable(TABLES.log, { enabled: allowed && (tab === "log" || tab === "papan"), order: "at", limit: tab === "log" ? 3000 : 40 });

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
        unchecked ? "(Jawapan ini ditulis AI dan belum disemak: jangan tambah fakta khusus yang tiada di sini.)" : ""].filter(Boolean).join("\n\n"),
    };
  }
  const { settings, save, loading: settingsLoading, error: settingsError } = useSettings(allowed);
  useEffect(() => { setWanshah(approvedPoses(settings.wanshah)); }, [settings.wanshah]);   // Wanshah (supabase/040) replaces the poses in place
  // My designs (supabase/027): the saved text-free designs and the default, offered to every look picker through one context
  const designsCtx = useMemo(() => ({
    designs: Array.isArray(settings.designs) ? settings.designs.filter((d) => d && typeof d === "object" && d.id) : [],
    defaultId: String(settings.default_design?.id || ""), ready: Array.isArray(settings.designs),
    saveDesigns: (list) => save("designs", list), setDefault: (id) => save("default_design", id ? { id } : {}),
  }), [settings, save]);
  const brand = useMemo(() => brandOf(settings), [settings]);
  const [guideOpen, setGuideOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);       // the phone's slide-over menu (AppSidebar's MobileDrawer)

  function go(next) {
    setTab(next); window.location.hash = next === "papan" ? "" : next;
  }
  // the sidebar on wide screens: auto (a rail of icons that slides open on hover) unless Wan pins it. Auto is the
  // default (Wan, 27 Sep 2026: "make the sidebar auto mode the default"); the choice is remembered on this browser
  // under a new key, so a "pinned" saved while pinned was still the default does not hide the new default.
  const NAV_KEY = "semasa.sidebar.v2";
  const [navMode, setNavMode] = useState(() => {
    try { return localStorage.getItem(NAV_KEY) === "pinned" ? "pinned" : "auto"; } catch { return "auto"; }
  });
  function toggleNav() {
    setNavMode((m) => {
      const next = m === "auto" ? "pinned" : "auto";
      try { localStorage.setItem(NAV_KEY, next); } catch { /* private window */ }
      return next;
    });
  }
  const counts = {
    idea: ideas.rows.filter((r) => r.status === "new").length,
    post: posts.rows.filter((r) => r.status === "draft").length,
  };
  const gate = (node) => <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6"><Gate user={user} ready={ready} canUpload={canUpload} onToast={push}>{node}</Gate></main>;

  // a client's "view online" link: the paper and nothing else, no sign-in, no menu
  if (pubToken && configured) return <Suspense fallback={<Waiting />}><BillingPublic token={pubToken} /></Suspense>;
  if (unsubToken && configured) return <Suspense fallback={<Waiting />}><CrmUnsubscribe token={unsubToken} /></Suspense>;

  let body;
  if (!configured) body = <Unconfigured />;
  else if (tab === "idea") body = allowed ? <IdeasTab ideas={ideas} posts={posts} user={user} brand={brand} onToast={push}
    openPost={(id) => { setFocusPost(id); go("post"); }} /> : gate(null);
  else if (tab === "post") body = allowed ? <PostsTab posts={posts} media={gens} log={log} brand={brand} user={user}
    settings={settings} onToast={push} focusId={focusPost} setFocusId={setFocusPost} /> : gate(null);
  else if (tab === "media") body = allowed ? <MediaTab user={user} gens={gens} prompts={prompts} onToast={push} go={go} /> : gate(null);
  else if (tab === "media-lib") body = allowed ? <ImageLibraryTab user={user} gens={gens} posts={posts} onToast={push} go={go} /> : gate(null);
  else if (tab === "design") body = allowed ? <DesignTab user={user} gens={gens} posts={posts} brand={brand} settings={settings} saveSetting={save} onToast={push} go={go} /> : gate(null);
  else if (tab === "design-lib") body = allowed ? <DesignTab view="library" user={user} gens={gens} posts={posts} brand={brand} settings={settings} saveSetting={save} onToast={push} go={go} /> : gate(null);
  else if (tab === "wangian") body = allowed ? <FragranceTab user={user} gens={gens} onToast={push} /> : gate(null);
  else if (tab === "video") body = allowed ? <VideoTab user={user} gens={gens} brand={brand} onToast={push} prompts={prompts} go={go}
    openPost={(id) => { setFocusPost(id); go("post"); }} /> : gate(null);
  else if (tab === "video-lib") body = allowed ? <VideoLibraryTab user={user} gens={gens} posts={posts} onToast={push} go={go} /> : gate(null);
  else if (tab === "motion-skills") body = allowed ? <MotionSkillsTab user={user} settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "chat") body = allowed ? <ChatTab /> : gate(null);
  else if (tab === "memori") body = allowed ? <MemoryTab settings={settings} settingsLoading={settingsLoading} settingsError={settingsError} save={save} onToast={push} /> : gate(null);
  else if (tab === "otak") body = allowed ? <BrainTab user={user} settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "wang") body = allowed ? <MoneyTab user={user} /> : gate(null);
  else if (tab === "bil") body = allowed ? <BillingTab user={user} settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "bil-valorith") body = allowed ? <BillingTab key="valorith" lockBusiness="valorith" user={user} settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "syarikat") body = allowed ? <BusinessesTab settings={settings} onToast={push} go={go} /> : gate(null);
  else if (tab === "hooks") body = allowed ? <HooksTab settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "gaya") body = allowed ? <WritingStylesTab settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "stack") body = allowed ? <StackTab onToast={push} go={go} /> : gate(null);
  else if (tab === "langganan") body = allowed ? <SubscriptionsTab user={user} onToast={push} /> : gate(null);
  else if (tab === "resit") body = allowed ? <ResitTab user={user} onToast={push} /> : gate(null);
  else if (tab === "crm") body = allowed ? <CrmTab user={user} settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "tech") body = allowed ? <TechOverviewTab go={go} /> : gate(null);
  else if (tab === "office") body = allowed ? <OfficeTab settings={settings} save={save} onToast={push} user={user} /> : gate(null);
  else if (tab === "repo") body = allowed ? <RepoTab settings={settings} save={save} onToast={push} user={user} /> : gate(null);
  else if (tab === "api") body = allowed ? <ApiTab settings={settings} save={save} onToast={push} /> : gate(null);
  else if (tab === "prestasi") body = allowed ? <PrestasiTab posts={posts} go={(to, postId) => { if (postId) setFocusPost(postId); go(to); }} /> : gate(null);
  else if (tab === "papan") body = allowed ? <HomeTab ideas={ideas} posts={posts} log={log} activity={activity} brand={brand} user={user} settings={settings} save={save} onToast={push}
    go={(to, postId) => { if (postId) setFocusPost(postId); go(to); }} /> : gate(null);
  else if (tab === "faq") body = allowed ? <FaqTab faqs={faqs} settings={settings} brand={brand} user={user} onToast={push}
    onPost={(r) => setIdeaFrom(faqIdea(r))} /> : gate(null);
  else if (tab === "log") body = allowed ? <LogTab log={activity} onOpen={(to) => { if (to.postId) setFocusPost(to.postId); go(to.tab); }} /> : gate(null);
  else if (tab === "dokumen") body = allowed ? <DocsTab /> : gate(null);
  else if (tab === "tetapan") body = allowed ? <SettingsTab settings={settings} brand={brand} save={save} onToast={push} /> : gate(null);
  else body = <IsuTab trends={trends} onToast={push} onIdea={allowed ? setIdeaFrom : undefined} onFaq={allowed ? faqFrom : undefined}
    allowed={allowed} gateNode={allowed ? null : gate(null)} settings={settings} save={save} brand={brand} user={user} />;

  return (
    <DesignsContext.Provider value={designsCtx}>
    <div id="top" className="app-shell min-h-screen lg:flex">
      <AppSidebar tab={tab} setTab={go} user={user} counts={allowed ? counts : {}} mode={navMode} onToggleMode={toggleNav}
        drawerOpen={menuOpen} onCloseDrawer={() => setMenuOpen(false)} />
      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
      <Header tab={tab} setTab={go} user={user} sidebar navMode={navMode} onToggleSidebar={toggleNav}
        onGuide={allowed ? () => setGuideOpen(true) : undefined} onMenu={() => setMenuOpen(true)} />
      {allowed && <Guide open={guideOpen} onClose={() => setGuideOpen(false)} settings={settings} brand={brand} />}
      <div className="flex-1">
        {allowed && configured && <SegmentBar tab={tab} setTab={go} />}
        <Suspense fallback={<Waiting />}>{body}</Suspense>
      </div>
      {allowed && (
        <Suspense fallback={null}>
          <IdeaComposer open={Boolean(ideaFrom)} onClose={() => setIdeaFrom(null)} trend={ideaFrom} user={user} brand={brand}
            onToast={push} onDone={() => ideas.reload()} />
        </Suspense>
      )}
      {/* the news footer belongs to the issues page; on every other page it was a line about something not on screen */}
      {tab === "isu" && <footer className="mt-auto border-t border-line py-8 text-center text-[11px] text-muted">
        {t("Semasa · sumber berita kekal milik penerbit masing-masing · dikemas kini setiap 8 jam · "
          + "isu yang tidak dijadikan idea hilang selepas 48 jam",
        "Semasa · news sources remain the property of their publishers · updated every 8 hours · "
          + "issues not turned into an idea disappear after 48 hours")}
      </footer>}
      </div>
      {/* phone and installed-app shortcuts: only once signed in, so the sign-in screen stays one card */}
      {allowed && configured && <MobileTabBar tab={tab} setTab={go} />}
      {/* the install hint on the home page only (also the sign-in screen, which is the home address), under any open dialog */}
      {tab === "papan" && <InstallHint />}
      <Toasts toasts={toasts} />
    </div>
    </DesignsContext.Provider>
  );
}

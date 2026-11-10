/* Senarai teknologi (Wan, 11 Oct 2026, Phase 4: "repo registration, repo library dengan URL, API library dan model dia, satu
   senarai semua API/SDK/CLI"). ONE list, built from what is already true:
     - APIs: every outside service a worker holds a key for (CODE_APIS; stack.test.mjs fails when a workflow uses a secret no
       entry names, or an entry names one no workflow uses) plus the AI gateways the probe reads, with their models
       (semasa_api_status);
     - SDKs: web/package.json and backend/requirements.txt (PY_PACKAGES, checked line by line against that file);
     - CLIs: the tools the workflows run (CLIS, each checked against .github/workflows);
     - repos: the office repos (semasa_repos) and the repo library (semasa_repo_library), each with its URL;
     - and what Wan adds by hand (semasa_tech_items, supabase/068).
   Pure, so stack.test.mjs runs it under Node. A secret's NAME is shown, never its value (the page never holds one). */

export const KINDS = ["api", "sdk", "cli", "repo", "service"];
export const KIND_WORDS = { api: ["API", "API"], sdk: ["SDK", "SDK"], cli: ["CLI", "CLI"], repo: ["Repo", "Repo"], service: ["Servis", "Service"] };
export const SOURCE_WORDS = {
  code: ["dalam kod", "in the code"], probe: ["diperiksa", "probed"], mine: ["tambahan saya", "added by me"],
  office: ["repo pejabat", "office repo"], library: ["pustaka repo", "repo library"], web: ["web/package.json", "web/package.json"],
  python: ["requirements.txt", "requirements.txt"],
};

// Outside services, by the credential each worker reads. `env`: the secret names in .github/workflows; `store`: a key held in
// the database instead (Wan pastes it on a page); `probe`: the semasa_api_status slug whose models belong to this entry.
export const CODE_APIS = [
  { id: "supabase", name: "Supabase", env: ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ACCESS_TOKEN", "PULSE_SECRET"], url: "https://supabase.com", docs: "https://supabase.com/docs",
    used: ["Pangkalan data, storan fail dan log masuk; setiap pekerja dan halaman. Token akses menghantar Edge Functions; PULSE_SECRET ialah rahsia jam denyut API (sama dengan Vault semasa_pulse_secret).", "Database, file storage and sign-in; every worker and page. The access token deploys the Edge Functions; PULSE_SECRET is the API pulse clock's secret (the same value as Vault semasa_pulse_secret)."] },
  { id: "llm", name: "Gerbang AI (penulis utama dan sandaran)", env: ["LLM_API_KEY", "LLM_FALLBACK_API_KEY"], url: "", docs: "",
    used: ["Kunci penulis utama dan sandaran; gerbang dan model yang diperiksa disenaraikan di bawah.", "The primary and backup writers' keys; the gateways and models the probe reads are listed below."] },
  { id: "openai", name: "OpenAI", env: ["OPENAI_API_KEY"], url: "https://platform.openai.com", docs: "https://platform.openai.com/docs",
    used: ["Gambar dan video (providers/openai_images.py); penulis gantian bila ditetapkan.", "Images and video (providers/openai_images.py); a stand-in writer when set."] },
  { id: "anthropic", name: "Anthropic", env: ["ANTHROPIC_API_KEY"], url: "https://console.anthropic.com", docs: "https://docs.anthropic.com",
    used: ["Penulis gantian bila ditetapkan (config.py).", "A stand-in writer when set (config.py)."] },
  { id: "gemini", name: "Google Gemini", env: [], store: "semasa_gemini_keys", probe: "gemini", url: "https://ai.google.dev", docs: "https://ai.google.dev/gemini-api/docs",
    used: ["Gambar dan pembaca; beberapa kunci, dipilih oleh pasukan AI (kunci disimpan di halaman API).", "Pictures and the reader; several keys, picked by the AI team (keys held on the API page)."] },
  { id: "chatgpt", name: "ChatGPT (log masuk Wan)", env: [], store: "semasa_chatgpt_auth", url: "https://chatgpt.com", docs: "",
    used: ["Gambar dan storyboard Motion melalui log masuk ChatGPT Wan.", "Motion's pictures and storyboard through Wan's ChatGPT login."] },
  { id: "composio", name: "Composio", env: ["COMPOSIO_CONSUMER_KEY", "COMPOSIO_API_KEY"], url: "https://composio.dev", docs: "https://docs.composio.dev",
    used: ["Gmail (bil, CRM), LinkedIn, resit dan sumber Wan (Reddit, YouTube, OneDrive).", "Gmail (billing, CRM), LinkedIn, receipts and Wan's sources (Reddit, YouTube, OneDrive)."] },
  { id: "buffer", name: "Buffer", env: ["BUFFER_API_KEY"], url: "https://buffer.com", docs: "https://developers.buffer.com",
    used: ["Menerbit ke Facebook, Instagram dan Threads, dan membaca metrik.", "Publishes to Facebook, Instagram and Threads, and reads the metrics."] },
  { id: "zernio", name: "Zernio", env: ["ZERNIO_API_KEY_1", "ZERNIO_API_KEY_2", "ZERNIO_API_KEY_3"], url: "https://zernio.com", docs: "https://docs.zernio.com",
    used: ["Menerbit ke Instagram, Threads, Facebook, LinkedIn dan TikTok (tiga log masuk; tutup sehingga dihidupkan).", "Publishes to Instagram, Threads, Facebook, LinkedIn and TikTok (three logins; off until switched on)."] },
  { id: "unsplash", name: "Unsplash", env: ["UNSPLASH_ACCESS_KEY"], url: "https://unsplash.com/developers", docs: "https://unsplash.com/documentation",
    used: ["Gambar stok untuk post dan Motion.", "Stock photos for posts and Motion."] },
  { id: "replicate", name: "Replicate", env: ["REPLICATE_API_TOKEN"], url: "https://replicate.com", docs: "https://replicate.com/docs",
    used: ["Imej-ke-imej dan imej-ke-video (providers/replicate.py).", "Image-to-image and image-to-video (providers/replicate.py)."] },
  { id: "cloudflare", name: "Cloudflare Workers AI", env: ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"], url: "https://developers.cloudflare.com/workers-ai/", docs: "https://developers.cloudflare.com/workers-ai/models/",
    used: ["Gambar percuma (10,000 neuron sehari) untuk post dan Motion.", "Free pictures (10,000 neurons a day) for posts and Motion."] },
  { id: "github", name: "GitHub API", env: ["REPOS_TOKEN", "LANDING_REPO_TOKEN", "GITHUB_TOKEN"], url: "https://github.com", docs: "https://docs.github.com/rest",
    used: ["Repo pejabat, pustaka repo, repo Motion dan Nota regulatori di halaman utama.", "Office repos, the repo library, Motion's repos and the landing page's Nota regulatori."] },
  { id: "sheet", name: "Google Apps Script (Semasa Sheet)", env: ["SEMASA_SHEET_URL", "SEMASA_SHEET_TOKEN"], url: "https://developers.google.com/apps-script", docs: "https://developers.google.com/apps-script",
    used: ["Cermin FAQ dan Log dalam Google Sheet.", "Mirrors the FAQ and the Log in a Google Sheet."] },
  { id: "telegram", name: "Telegram Bot API", env: ["TELEGRAM_BOT_TOKEN"], url: "https://core.telegram.org/bots", docs: "https://core.telegram.org/bots/api",
    used: ["Calon FAQ daripada kumpulan Telegram; tidur sehingga token diberi.", "FAQ candidates from Telegram groups; dormant until a token is given."] },
  { id: "youtube", name: "YouTube (yt-dlp)", env: ["YTDLP_COOKIES"], url: "https://github.com/yt-dlp/yt-dlp", docs: "https://github.com/yt-dlp/yt-dlp#usage-and-options",
    used: ["Klip YouTube untuk video.", "YouTube clips for video."] },
  { id: "edge-tts", name: "Microsoft Edge TTS", env: [], url: "https://github.com/rany2/edge-tts", docs: "", kind: "service",
    used: ["Suara narrator Motion (tanpa kunci); gTTS sebagai sandaran.", "Motion's narrator voice (no key); gTTS as the fallback."] },
];

// The tools the workflows run. `find` is matched against every workflow file (stack.test.mjs).
export const CLIS = [
  { id: "python", name: "Python", find: /actions\/setup-python/, url: "https://www.python.org", used: ["Menjalankan setiap pekerja backend/semasa.", "Runs every backend/semasa worker."] },
  { id: "node", name: "Node.js + npm", find: /actions\/setup-node/, url: "https://nodejs.org", used: ["Membina dan menguji halaman web (Vite).", "Builds and tests the web page (Vite)."] },
  { id: "ffmpeg", name: "FFmpeg (ffmpeg, ffprobe)", find: /\bffmpeg\b/, url: "https://ffmpeg.org", used: ["Menyunting dan mengukur audio dan video Motion.", "Edits and measures Motion's audio and video."] },
  { id: "playwright", name: "Playwright Chromium", find: /playwright install/, url: "https://playwright.dev", used: ["Membaca halaman yang perlukan JavaScript (scraper, Otak AI).", "Reads pages that need JavaScript (the scraper, AI brain)."] },
  { id: "supabase-cli", name: "Supabase CLI", find: /supabase\/setup-cli/, url: "https://supabase.com/docs/guides/cli", used: ["Menghantar Edge Functions.", "Deploys the Edge Functions."] },
  { id: "git", name: "git", find: /\bgit clone\b/, url: "https://git-scm.com", used: ["Menyalin repo semasa kerja (Nota regulatori, ujian SadTalker).", "Clones repos during a job (Nota regulatori, the SadTalker probe)."] },
  { id: "actions", name: "GitHub Actions", find: /actions\/checkout/, url: "https://docs.github.com/actions", kind: "service", used: ["Menjalankan setiap kerja berjadual dan yang dikejutkan oleh pangkalan data.", "Runs every scheduled job and every job the database wakes."] },
];

// backend/requirements.txt, name and version range, in file order (stack.test.mjs reads the file and compares).
export const PY_PACKAGES = [
  ["supabase", ">=2.10,<3"], ["playwright", ">=1.47"], ["beautifulsoup4", ">=4.12"], ["lxml", ">=5"], ["feedparser", ">=6.0.11"],
  ["requests", ">=2.32"], ["pillow", ">=10"], ["yt-dlp[default]", ">=2026.8.19"], ["imageio-ffmpeg", ">=0.6"], ["gdown", ">=5.2"],
  ["pypdf", ">=5.0"], ["segno", ">=1.6"], ["edge-tts", ">=7.2"], ["gTTS", ">=2.5"],
];

const pypi = (name) => `https://pypi.org/project/${name.replace(/\[.*$/, "")}/`;
const npmUrl = (name) => `https://www.npmjs.com/package/${name}`;
const clean = (v) => String(v || "").replace(/^[\^~]/, "");
const pair = (x, L) => (Array.isArray(x) ? x[L] || x[0] : x || "");

/** The probe's models for a gateway row (strings only, "models/" dropped, the configured one first). */
export function modelsOf(row) {
  const list = (Array.isArray(row?.models) ? row.models : []).map((m) => String(typeof m === "string" ? m : m?.id || "").replace(/^models\//, "")).filter(Boolean);
  const first = String(row?.model || "").replace(/^models\//, "");
  const uniq = [...new Set(list)];
  return first && uniq.includes(first) ? [first, ...uniq.filter((m) => m !== first)] : uniq;
}

/** A probe row's state: up (answered), models (reached, the model did not answer), down, nokey. */
export function liveOf(row) {
  if (!row) return "";
  if (row.key_set === false) return "nokey";
  if (row.chat_ok) return "up";
  if (row.reachable) return "models";
  return "down";
}

/** Every row of the one list. `L` is 0 (BM) or 1 (EN). */
export function buildStack({ pkg = {}, probe = [], repos = [], library = [], mine = [] } = {}, L = 0) {
  const rows = [];
  const probeBy = Object.fromEntries((probe || []).map((r) => [r.slug, r]));
  const claimed = new Set();
  for (const a of CODE_APIS) {
    const p = a.probe ? probeBy[a.probe] : null;
    if (p) claimed.add(a.probe);
    rows.push({ key: `code:${a.id}`, kind: a.kind || "api", name: a.name, version: "", url: a.url, docs: a.docs || "", env: a.env, store: a.store || "",
      models: p ? modelsOf(p) : [], used: pair(a.used, L), source: "code", status: "active", live: p ? liveOf(p) : "" });
  }
  for (const p of probe || []) {
    if (claimed.has(p.slug)) continue;
    rows.push({ key: `probe:${p.slug}`, kind: "api", name: p.name || p.slug, version: p.model ? String(p.model).replace(/^models\//, "") : "", url: p.base_url || "", docs: "",
      env: [], store: "", models: modelsOf(p), used: [L ? "AI gateway" : "Gerbang AI", p.role].filter(Boolean).join(" · "), source: "probe", status: "active", live: liveOf(p) });
  }
  for (const c of CLIS) rows.push({ key: `cli:${c.id}`, kind: c.kind || "cli", name: c.name, version: "", url: c.url, docs: "", env: [], store: "", models: [], used: pair(c.used, L), source: "code", status: "active", live: "" });
  const deps = { ...(pkg.dependencies || {}) };
  const dev = { ...(pkg.devDependencies || {}) };
  for (const [n, v] of Object.entries(deps)) rows.push({ key: `npm:${n}`, kind: "sdk", name: n, version: clean(v), url: npmUrl(n), docs: "", env: [], store: "", models: [], used: L ? "web page" : "halaman web", source: "web", status: "active", live: "" });
  for (const [n, v] of Object.entries(dev)) rows.push({ key: `npm:${n}`, kind: "sdk", name: n, version: clean(v), url: npmUrl(n), docs: "", env: [], store: "", models: [], used: L ? "web build" : "binaan web", source: "web", status: "active", live: "" });
  for (const [n, v] of PY_PACKAGES) rows.push({ key: `py:${n}`, kind: "sdk", name: n, version: v, url: pypi(n), docs: "", env: [], store: "", models: [], used: L ? "Python workers" : "pekerja Python", source: "python", status: "active", live: "" });
  for (const r of repos || []) rows.push({ key: `office:${r.full_name}`, kind: "repo", name: r.full_name, version: r.default_branch || "", url: r.html_url || `https://github.com/${r.full_name}`, docs: "",
    env: [], store: "", models: [], used: r.description || "", source: "office", status: "active", live: r.error ? "down" : r.ci === "red" ? "models" : r.ci === "green" ? "up" : "" });
  const office = new Set((repos || []).map((r) => String(r.full_name || "").toLowerCase()));
  for (const r of library || []) {
    if (r.full_name && office.has(String(r.full_name).toLowerCase())) continue;
    rows.push({ key: `lib:${r.id}`, kind: "repo", name: r.full_name || r.name || r.url, version: r.category || "", url: r.html_url || r.url, docs: "", env: [], store: "", models: [],
      used: pair([r.summary_bm, r.summary_en], L) || r.description || "", source: "library", status: r.archived ? "retired" : "active", live: "" });
  }
  for (const m of mine || []) rows.push({ id: m.id, key: `mine:${m.id}`, kind: m.kind, name: m.name, version: "", url: m.url || "", docs: m.docs_url || "", env: m.env_key ? [m.env_key] : [], store: "",
    models: Array.isArray(m.models) ? m.models : [], used: m.used_for || "", notes: m.notes || "", source: "mine", status: m.status || "active", live: "" });
  return rows;
}

/** How many rows of each kind (and "all"). */
export function countByKind(rows) {
  const out = { all: rows.length };
  for (const k of KINDS) out[k] = rows.filter((r) => r.kind === k).length;
  return out;
}

/** Rows of `kind` ("all" for every one) whose name, purpose, models, secret names or address hold `q`. */
export function filterStack(rows, kind = "all", q = "") {
  const needle = String(q || "").trim().toLowerCase();
  return rows.filter((r) => (kind === "all" || r.kind === kind)
    && (!needle || [r.name, r.used, r.url, r.version, ...(r.models || []), ...(r.env || [])].some((x) => String(x || "").toLowerCase().includes(needle))));
}

/** The row Wan's form saves (semasa_tech_items), or {error}: a name, http(s) addresses, a secret NAME (never a value), models one a
    line or comma-separated. */
export function itemRow(f, t) {
  const name = String(f.name || "").trim().slice(0, 80);
  if (!name) return { error: t("Tulis nama dahulu.", "Write a name first.") };
  if (!["api", "sdk", "cli", "service"].includes(f.kind)) return { error: t("Pilih jenis.", "Choose a kind.") };
  const url = String(f.url || "").trim();
  const docs = String(f.docs_url || "").trim();
  if (url && !/^https?:\/\/\S+$/.test(url)) return { error: t("Alamat mesti bermula dengan https://", "The address must start with https://") };
  if (docs && !/^https?:\/\/\S+$/.test(docs)) return { error: t("Alamat dokumen mesti bermula dengan https://", "The docs address must start with https://") };
  const env = String(f.env_key || "").trim();
  if (env && !/^[A-Z][A-Z0-9_]{1,63}$/.test(env))
    return { error: t("Nama rahsia sahaja, huruf besar (cth OPENAI_API_KEY). Jangan tampal kunci itu sendiri.", "The secret's NAME only, in capitals (e.g. OPENAI_API_KEY). Never paste the key itself.") };
  const models = [...new Set(String(f.models || "").split(/[\n,]/).map((m) => m.trim()).filter(Boolean))].slice(0, 100);
  return { row: { kind: f.kind, name, url, docs_url: docs, env_key: env, models, used_for: String(f.used_for || "").trim().slice(0, 300),
    status: ["active", "trial", "retired"].includes(f.status) ? f.status : "active", notes: String(f.notes || "").trim().slice(0, 1000) } };
}

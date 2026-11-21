import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Brain, Check, ExternalLink, Eye, EyeOff, GraduationCap, Lightbulb, Loader2, Plus, RefreshCw, Search, Settings2, Sparkles, Trash2, UserPlus, Users, X } from "lucide-react";
import { fadeUp, stagger } from "../design/motion";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { stampMYT } from "../lib/format";
import { LIGHT_NAME, LIGHT_TINT, checkedText, lightOf } from "../lib/sourceLights";
import { MAX_HANDLES, PLATFORMS, PLATFORM_NAMES, accountOf, addCategory, addHandle, brainRow, canSearchAgain, chainParts, configOf, dismissSuggestion, notInBrain,
  ownerStats, patchCategory, readLoad, removeCategory, removeHandle, requestDiscovery, rowsFor, setAccountNames, suggestionsFor, togglePlatform } from "../lib/experts";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Skeleton from "../components/ui/Skeleton";
import SourceLight from "../components/SourceLight";
import { Input, Label, TextArea } from "../components/ui/Field";
import { useView } from "../components/ViewToggle";

/* Kandungan pakar / Expert content (Wan, 14 Nov 2026: "add another segment Expert Content, under it put AI Expert, Halal
   Expert (will be add more later) - in every subsegment I can add handler username and you will scrape their post (threads, fb,
   ig - I can select during username register ...) ... put original post and summary - can put as Idea ... automatically send to
   AI brain as reference only for AI expert ... list handler that worth to follow ... after add, the name remove from list").

   One page, a sub-tab per category. The posts are the page's daily work, so they come first on a phone and the three cards
   that manage a category (who is followed, who is worth following, its settings) open from "Manage accounts"; from `lg` up
   the cards stand beside the posts. The page saves settings.experts and nothing else; the sweep
   (backend/semasa/experts.py, a part of the Sources workflow) does the reading, twice a day and on "Sweep now".

   A save never writes what this page happened to be holding: it reads the row as it is NOW, applies the one change to that,
   and saves the result, so a handle added on the phone is not undone by a save from the desktop a minute later. */

const MIGRATION = ["Jalankan supabase/082_expert_content.sql sekali dahulu.", "Run supabase/082_expert_content.sql once first."];
const PLATFORM_TONE = { threads: "bg-ink text-bg", facebook: "bg-[#1877F2] text-white", instagram: "bg-[#C13584] text-white" };
const profileUrl = (platform, handle) => ({ threads: `https://www.threads.com/@${handle}`, facebook: `https://www.facebook.com/${handle}`,
  instagram: `https://www.instagram.com/${handle}/` })[platform];

function PlatformPicks({ value, onChange, disabled }) {
  return (
    <span className="flex flex-wrap gap-1.5" role="group">
      {PLATFORMS.map((p) => {
        const on = value.includes(p);
        return (
          <button type="button" key={p} aria-pressed={on} disabled={disabled} onClick={() => onChange(on ? value.filter((x) => x !== p) : [...value, p])}
            className={`inline-flex min-h-[36px] items-center gap-1.5 rounded-pill border px-3 py-1 text-xs font-medium transition disabled:opacity-50 ${on ? "border-accent bg-accent/10 text-ink" : "border-line bg-surface text-muted hover:text-ink"}`}>
            <span className={`grid h-3.5 w-3.5 place-items-center rounded-[4px] border ${on ? "border-accent bg-accent text-accent-ink" : "border-line"}`}>{on && <Check size={10} strokeWidth={3} />}</span>
            {PLATFORM_NAMES[p]}
          </button>
        );
      })}
    </span>
  );
}

/* What the last sweep said about one account on one platform: posts read, an error in words, why it gave nothing, or nothing yet. */
function lastRead(report, name, platform) {
  const label = `@${name} (${PLATFORM_NAMES[platform]})`.toLowerCase();
  const find = (map) => Object.entries(map || {}).find(([k]) => k.toLowerCase() === label);
  const err = (report?.errors || []).find((e) => String(e).toLowerCase().startsWith(`${label}:`));
  if (err) return { state: "red", text: String(err).slice(label.length + 1).trim() };
  const by = find(report?.by_handle);
  const note = find(report?.notes);
  if (by) return { state: by[1] > 0 ? "green" : "orange", n: by[1], ...(note ? { text: note[1] } : {}) };
  return { state: "unknown" };
}

/* One username field per ticked platform: the owner can be called something else on each (Wan, 15 Nov 2026). Empty = the main name. */
function NameFields({ platforms, names, main, onChange, disabled }) {
  const { t } = useLang();
  if (platforms.length < 1) return null;
  return (
    <div className="space-y-1.5" data-name-fields>
      {platforms.map((p) => (
        <label key={p} className="flex items-center gap-2">
          <span className="w-[4.75rem] shrink-0 text-[11px] font-medium text-muted">{PLATFORM_NAMES[p]}</span>
          <span className="text-muted">@</span>
          <Input value={names[p] || ""} disabled={disabled} onChange={(e) => onChange(p, e.target.value)} data-name-input={p}
            placeholder={main.trim().replace(/^@+/, "") || t("sama", "same")} autoCapitalize="none" autoCorrect="off" spellCheck={false}
            aria-label={t("Nama pengguna di {p}", "Username on {p}", { p: PLATFORM_NAMES[p] })} className="min-w-0 flex-1 !py-1.5 !text-xs" />
        </label>
      ))}
    </div>
  );
}

function HandleRow({ h, report, stats, active, busy, onToggle, onRemove, onName, onShow }) {
  const { t } = useLang();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const differs = Object.keys(h.names || {}).length > 0;
  function open() { setDraft({ ...(h.names || {}) }); setEditing(true); }
  async function saveNames() {
    // one save for every platform: a save per platform would each start from the same stored copy and undo the one before
    if (await onName(h.handle, draft)) setEditing(false);
  }
  const reads = PLATFORMS.filter((p) => h.platforms.includes(p)).map((p) => ({ p, last: lastRead(report, accountOf(h, p), p) }));
  const why = reads.find((x) => x.last.state === "red") || reads.find((x) => x.last.state === "orange" && x.last.text);
  const s = stats || { shown: 0, hidden: 0, off: 0 };
  return (
    <li className={`rounded-tile border bg-bg/60 p-3 ${active ? "border-accent" : "border-line/70"}`} data-handle={h.handle}>
      <div className="flex items-center justify-between gap-2">
        {/* the name opens this owner's posts: the feed's own filter, one press away */}
        <button type="button" onClick={() => onShow(h.handle)} aria-pressed={active} data-show-owner
          title={active ? t("Tunjuk semua akaun", "Show every account") : t("Tunjuk catatan @{h} sahaja", "Show only @{h}'s posts", { h: h.handle })}
          className="min-w-0 truncate text-left text-sm font-semibold text-ink hover:text-accent">@{h.handle}</button>
        <button type="button" disabled={busy} onClick={() => onRemove(h.handle)} aria-label={t("Buang @{h}", "Remove @{h}", { h: h.handle })}
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-muted transition hover:bg-danger/10 hover:text-danger disabled:opacity-50"><Trash2 size={14} /></button>
      </div>
      {/* what is in the feed from this owner, so "0 posts" can be told from "everything judged off the field" */}
      <p className="text-[11px] tabular-nums text-muted" data-owner-stats>
        {t("{n} dipapar", "{n} shown", { n: s.shown })}
        {s.off > 0 && <> · {t("{n} luar bidang", "{n} off the field", { n: s.off })}</>}
        {s.hidden > 0 && <> · {t("{n} anda sorok", "{n} hidden by you", { n: s.hidden })}</>}
      </p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {PLATFORMS.map((p) => {
          const on = h.platforms.includes(p);
          const last = on ? reads.find((x) => x.p === p).last : null;
          const only = on && h.platforms.length === 1;
          const said = !last ? t("tidak dibaca", "not read")
            : last.text ? last.text
            : last.state === "unknown" ? t("menunggu sapuan seterusnya", "waiting for the next sweep")
            : t("{n} catatan dalam sapuan lepas", "{n} post(s) in the last sweep", { n: last.n });
          return (
            <button type="button" key={p} aria-pressed={on} disabled={busy || only} onClick={() => onToggle(h.handle, p)}
              title={only ? t("Platform terakhir: buang akaun ini untuk berhenti.", "The last platform: remove the account to stop.") : `${PLATFORM_NAMES[p]}: ${said}`}
              className={`inline-flex min-h-[32px] items-center gap-1.5 rounded-pill px-2.5 py-1 text-[11px] font-medium transition disabled:cursor-default ${on ? LIGHT_TINT[last.state] + " text-ink" : "border border-dashed border-line text-muted hover:text-ink"}`}>
              {on && <SourceLight light={last.state} why={said} className="!h-2 !w-2" />}
              {PLATFORM_NAMES[p]}{on && h.names?.[p] ? ` @${h.names[p]}` : ""}{on && last.n !== undefined ? ` · ${last.n}` : ""}
            </button>
          );
        })}
      </div>
      {why && (
        <p className={`mt-2 flex gap-1.5 text-[11px] leading-snug [overflow-wrap:anywhere] ${why.last.state === "red" ? "text-danger" : "text-ink/75"}`} data-handle-why>
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />{PLATFORM_NAMES[why.p]}: {why.last.text}</p>
      )}
      {editing ? (
        <div className="mt-3 rounded-tile bg-surface-2 p-2.5">
          <p className="mb-2 text-[11px] leading-snug text-muted">{t("Nama pengguna di setiap platform. Kosongkan jika sama dengan @{h}.", "The username on each platform. Leave it empty if it is the same as @{h}.", { h: h.handle })}</p>
          <NameFields platforms={h.platforms} names={draft} main={h.handle} disabled={busy} onChange={(p, v) => setDraft((d) => ({ ...d, [p]: v }))} />
          <div className="mt-2.5 flex gap-2">
            <Button size="sm" disabled={busy} onClick={saveNames} data-save-names>{t("Simpan", "Save")}</Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>{t("Batal", "Cancel")}</Button>
          </div>
        </div>
      ) : (
        <button type="button" disabled={busy} onClick={open} data-edit-names
          className="mt-2 inline-flex min-h-[32px] items-center gap-1 text-[11px] font-medium text-accent hover:underline disabled:opacity-50">
          {differs ? t("Ubah nama pengguna", "Edit usernames") : t("Nama pengguna berbeza di platform lain?", "A different username on another platform?")}</button>
      )}
    </li>
  );
}

/* The expert's own words. A chain is shown part by part, each numbered; closed, it is the first part with the count of the rest. */
function Original({ raw }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const parts = chainParts(raw.original);
  if (!parts.length) return null;
  const chain = parts.length > 1;
  const long = chain || parts[0].length > 420;
  const shown = open ? parts : parts.slice(0, 1);
  return (
    <figure className="mt-3 rounded-tile border-l-2 border-accent/60 bg-bg/70 py-2 pl-3 pr-2.5" data-original>
      <figcaption className="text-[11px] font-semibold text-muted">
        {chain ? t("Catatan asal · rantaian {n} bahagian", "Original post · a chain of {n} parts", { n: parts.length }) : t("Catatan asal", "Original post")}{raw.metrics ? ` · ${raw.metrics}` : ""}
      </figcaption>
      {shown.map((text, i) => (
        <div key={i} className={i ? "mt-2 border-t border-line/60 pt-2" : ""} data-part={i + 1}>
          {chain && <span className="mb-0.5 block text-[10px] font-semibold tabular-nums text-accent">{i + 1}/{parts.length}</span>}
          <blockquote className={`whitespace-pre-line text-[13px] leading-relaxed text-ink/90 [overflow-wrap:anywhere] ${!open ? "line-clamp-5" : ""}`}>{text}</blockquote>
        </div>
      ))}
      {long && (
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-original-toggle className="mt-1 inline-flex min-h-[32px] items-center text-xs font-medium text-accent hover:underline">
          {open ? t("Tunjuk kurang", "Show less") : chain ? t("Tunjuk semua {n} bahagian", "Show all {n} parts", { n: parts.length }) : t("Tunjuk semua", "Show all")}</button>
      )}
    </figure>
  );
}

function ExpertCard({ row, inBrain, busy, onIdea, onBrain, onHide }) {
  const { t } = useLang();
  const raw = row.raw || {};
  return (
    <motion.div variants={fadeUp} layout>
      <Card as="article" className={`overflow-hidden ${row.dismissed ? "opacity-60" : ""}`} data-expert-post={row.id}>
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-4">
          <span className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className={`rounded-pill px-2 py-0.5 text-[10px] font-semibold ${PLATFORM_TONE[raw.platform] || "bg-surface-2 text-ink"}`}>{PLATFORM_NAMES[raw.platform] || raw.platform}</span>
            <a href={profileUrl(raw.platform, raw.handle)} target="_blank" rel="noreferrer" className="truncate text-xs font-semibold text-ink hover:text-accent">@{raw.handle}</a>
            {raw.owner && raw.owner !== raw.handle && <span className="truncate text-[11px] text-muted" title={t("Pemilik akaun ini", "This account's owner")}>({raw.owner})</span>}
            {raw.parts > 1 && <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-ink/80" title={t("Rantaian catatan oleh pakar yang sama, digabungkan.", "A chain of posts by the same expert, joined.")}>{t("Rantaian · {n} catatan", "Thread · {n} posts", { n: raw.parts })}</span>}
            {inBrain && <span className="inline-flex items-center gap-1 rounded-pill bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent" title={t("Difailkan dalam Otak AI sebagai rujukan.", "Filed in the AI brain as a reference.")}><Brain size={10} /> {t("Otak AI", "AI brain")}</span>}
          </span>
          <time className="shrink-0 text-[11px] text-muted" title={row.created_at ? t("Dikutip {at}", "Collected {at}", { at: stampMYT(row.created_at) }) : ""}>{stampMYT(row.published_at || row.created_at)}</time>
        </div>
        <div className="px-4 pb-4 pt-3">
          <h3 className="[overflow-wrap:anywhere] font-display text-[17px] leading-snug text-ink">{row.title}</h3>
          <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-muted">{t("Ringkasan bot", "The bot's summary")}</p>
          <p className="mt-1 text-sm leading-relaxed text-ink/90 [overflow-wrap:anywhere]">{row.summary}</p>
          {row.why && (
            <p className="mt-3 rounded-tile bg-surface-2 p-2.5 text-[13px] leading-relaxed text-ink [overflow-wrap:anywhere]">
              <span className="block text-[11px] font-semibold text-muted">{t("Apa yang boleh diambil", "What to take from it")}</span>{row.why}
            </p>
          )}
          <Original raw={raw} />
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line/70 px-4 py-2">
          <button type="button" onClick={() => onIdea(row)} className="inline-flex min-h-[36px] items-center gap-1.5 whitespace-nowrap text-xs font-medium text-accent hover:underline"><Lightbulb size={13} /> {t("Jadikan idea", "Make an idea")}</button>
          {!inBrain && <button type="button" disabled={busy} onClick={() => onBrain(row)} className="inline-flex min-h-[36px] items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-ink disabled:opacity-50"><Brain size={13} /> {t("Hantar ke Otak AI", "Send to the AI brain")}</button>}
          {row.url && <a href={row.url} target="_blank" rel="noreferrer" className="inline-flex min-h-[36px] items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-ink"><ExternalLink size={13} /> {t("Buka catatan", "Open the post")}</a>}
          <button type="button" disabled={busy} onClick={() => onHide(row)} className="inline-flex min-h-[36px] items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-ink disabled:opacity-50">
            {row.dismissed ? <><Eye size={13} /> {t("Tunjuk semula", "Show again")}</> : <><EyeOff size={13} /> {t("Sembunyi", "Hide")}</>}</button>
        </div>
      </Card>
    </motion.div>
  );
}

export default function ExpertTab({ settings, save, user, onToast, onIdea, go }) {
  const { t, lang } = useLang();
  const en = lang === "en";
  const ready = settings.experts !== undefined;                    // the settings row exists only after supabase/082
  const saved = useMemo(() => configOf(settings.experts), [settings.experts]);
  const [local, setLocal] = useState(null);                        // what was just saved, shown until the settings read catches up
  useEffect(() => { setLocal(null); }, [settings.experts]);
  const cfg = local || saved;
  const [busy, setBusy] = useState(false);
  const [catRaw, setCat] = useView("pakar.category", "");
  const cat = cfg.categories.find((c) => c.id === catRaw) || cfg.categories[0] || null;

  const feed = useTable(TABLES.watch, { order: "published_at", limit: 600, realtime: false, everyMs: 120_000, eq: ["section", "expert"] });
  const [q, setQ] = useState("");
  const [who, setWho] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [sent, setSent] = useState(() => new Set());               // rows sent to the brain by hand in this visit
  const [busyId, setBusyId] = useState(null);
  const [manage, setManage] = useState(false);                     // a phone shows the posts; the three cards open from a button
  useEffect(() => { setWho(""); setQ(""); }, [cat?.id]);

  const [handle, setHandle] = useState("");
  const [plats, setPlats] = useState(["threads"]);
  const [names, setNames] = useState({});                          // a username that differs from the main one, per ticked platform
  const [newCat, setNewCat] = useState(null);                      // null = closed, a string = the name being typed
  const [form, setForm] = useState({ name: "", niche: "", keywords: "" });
  useEffect(() => { if (cat) setForm({ name: cat.name, niche: cat.niche, keywords: cat.keywords.join(", ") }); }, [cat?.id, settings.experts]); // eslint-disable-line react-hooks/exhaustive-deps

  const report = settings.sources?.report?.experts;
  const light = lightOf(settings.source_lights, "expert");
  const waiting = Boolean(settings.sources?.force);
  const load = readLoad(cfg);
  const suggestions = cat ? suggestionsFor(settings.expert_suggestions, cfg, cat.id) : [];
  const searched = cat ? settings.expert_suggestions?.seen?.[cat.id] : null;
  const again = canSearchAgain(cfg, settings.expert_suggestions);
  const rows = useMemo(() => (cat ? rowsFor(feed.rows, cat.id, { hidden: showHidden, q, handle: who }) : []), [feed.rows, cat, showHidden, q, who]);
  const counts = useMemo(() => Object.fromEntries(cfg.categories.map((c) => [c.id, rowsFor(feed.rows, c.id).length])), [feed.rows, cfg.categories]);
  const stats = useMemo(() => (cat ? ownerStats(feed.rows, cat.id) : {}), [feed.rows, cat]);
  const hiddenN = cat ? rowsFor(feed.rows, cat.id, { hidden: true }).length - rowsFor(feed.rows, cat.id).length : 0;
  const unsent = cat ? notInBrain(feed.rows, cat.id, sent) : [];
  const showManage = manage || (cat && !cat.handles.length);       // nothing followed yet: the cards are the page

  const ERRORS = {
    handle: t("Tulis nama akaun (tanpa ruang), atau tampal pautan profilnya.", "Type the account name (no spaces), or paste its profile link."),
    platform: t("Pilih sekurang-kurangnya satu platform.", "Tick at least one platform."),
    full: t("Had {n} akaun bagi satu kategori. Buang satu dahulu.", "A category holds {n} accounts. Remove one first.", { n: MAX_HANDLES }),
    name: t("Tulis nama kategori.", "Type the category's name."), exists: t("Kategori itu sudah ada.", "That category already exists."),
    category: t("Kategori itu sudah tiada. Muat semula halaman.", "That category is gone. Reload the page."),
  };

  /* Apply ONE change to the setting as it is stored now, then save. `change` takes a config and returns a config, or
     { cfg, ... } / { error } as lib/experts.js's adders do. Returns what `change` returned, or null when nothing was saved. */
  async function commit(change, done) {
    const before = local;
    setBusy(true);
    try {
      let base = cfg;
      const { data, error } = await supabase.from(TABLES.settings).select("key,value").eq("key", "experts").limit(1);
      const row = !error && (data || []).find((r) => r.key === "experts");
      if (row) base = configOf(row.value);
      const out = change(base);
      if (out && out.error) { onToast(ERRORS[out.error] || out.error, "danger"); return null; }
      const next = out && out.cfg ? out.cfg : out;
      setLocal(next);
      await save("experts", next);
      const said = typeof done === "function" ? done(out) : done;
      if (said) onToast(said, "ok");
      return out;
    } catch (e) {
      setLocal(before);
      onToast(/not found/.test(e.message) ? t(...MIGRATION) : e.message, "danger");
      return null;
    } finally { setBusy(false); }
  }

  async function register(e) {
    e?.preventDefault();
    if (!cat) return;
    const got = await commit((c) => addHandle(c, cat.id, handle, plats, names),
      (o) => (o.merged ? t("@{h} sudah ada: platform ditambah.", "@{h} was already there: the platforms were added.", { h: o.handle })
        : t("@{h} ditambah. Catatannya dibaca pada sapuan seterusnya.", "@{h} added. Its posts are read at the next sweep.", { h: o.handle })));
    if (got) { setHandle(""); setNames({}); }
  }
  const acceptSuggestion = (s) => commit((c) => addHandle(c, cat.id, s.handle, [PLATFORMS.includes(s.platform) ? s.platform : "threads"]),
    (o) => t("@{h} ditambah ke {c}.", "@{h} added to {c}.", { h: o.handle, c: cat.name }));
  async function createCategory(e) {
    e?.preventDefault();
    const got = await commit((c) => addCategory(c, newCat), t("Kategori ditambah. Isi bidangnya dan tambah akaun.", "Category added. Fill in its field and add accounts."));
    if (got) { setNewCat(null); setCat(got.id); setManage(true); }
  }
  async function dropCategory() {
    if (!cat || !window.confirm(t("Padam kategori “{c}” dan senarai akaunnya? Catatan yang sudah dikutip hilang dari halaman ini.", "Delete the category “{c}” and its account list? Posts already collected leave this page.", { c: cat.name }))) return;
    if (await commit((c) => removeCategory(c, cat.id), t("Kategori dipadam.", "Category deleted."))) setCat("");
  }
  const dirty = cat && (form.name.trim() !== cat.name || form.niche.trim() !== cat.niche || form.keywords.split(/[,\n]/).map((k) => k.trim()).filter(Boolean).join(", ") !== cat.keywords.join(", "));

  async function sweepNow(quiet = false) {
    try {
      await save("sources", { ...(settings.sources || {}), force: true });
      if (!quiet) onToast(t("Sapuan diminta. Ia mengambil beberapa minit.", "Sweep asked for. It takes a few minutes."), "ok");
      return true;
    } catch (e) { onToast(e.message, "danger"); return false; }
  }
  /* "Search again": the request's time goes in the setting (the sweep searches when it is newer than its last search), and a
     sweep is asked for so the answer comes in minutes, not at the next scheduled one. */
  async function searchAgain() {
    if (!again.ok) return;
    if (!(await commit((c) => requestDiscovery(c, new Date().toISOString())))) return;
    if (await sweepNow(true)) onToast(t("Carian diminta. Cadangan baharu muncul selepas sapuan, dalam beberapa minit.", "Search asked for. New suggestions appear after the sweep, in a few minutes."), "ok");
  }
  async function hide(r) {
    setBusyId(r.id);
    const { data, error } = await supabase.from(TABLES.watch).update({ dismissed: !r.dismissed }).eq("id", r.id).select("id");
    setBusyId(null);
    if (error || !data?.length) { onToast(error ? errText(error) : t("Tidak dapat diubah.", "Could not be changed."), "danger"); return; }
    feed.reload();
  }
  /* File rows in the AI brain as references, skipping an address already there. Returns how many went in. */
  async function fileInBrain(list) {
    const { data: there, error: e1 } = await supabase.from(TABLES.brainInbox).select("url").in("url", list.map((r) => r.url));
    if (e1) throw new Error(errText(e1));
    const known = new Set((there || []).map((x) => x.url));
    const fresh = list.filter((r) => !known.has(r.url));
    if (fresh.length) {
      const { error } = await supabase.from(TABLES.brainInbox).insert(fresh.map((r) => ({ ...brainRow(r), status: "pending", created_by: user?.id || null })));
      if (error) throw new Error(errText(error));
    }
    setSent((s) => new Set([...s, ...list.map((r) => r.id)]));
    return fresh.length;
  }
  async function toBrain(r) {
    setBusyId(r.id);
    try {
      const n = await fileInBrain([r]);
      onToast(n ? t("Dihantar ke Otak AI sebagai rujukan.", "Sent to the AI brain as a reference.") : t("Sudah ada dalam Otak AI.", "Already in the AI brain."), "ok");
    } catch (e) { onToast(e.message, "danger"); }
    finally { setBusyId(null); }
  }
  /* The switch only files what is read from now on; this sends what is already on the page, so the past is not left out silently. */
  async function sendExisting() {
    const list = unsent.slice(0, 40);
    if (!list.length) return;
    setBusy(true);
    try {
      const n = await fileInBrain(list);
      onToast(t("{n} catatan dihantar ke Otak AI sebagai rujukan ({k} sudah ada).", "{n} post(s) sent to the AI brain as references ({k} already there).", { n, k: list.length - n }), "ok");
    } catch (e) { onToast(e.message, "danger"); }
    finally { setBusy(false); }
  }
  const setBrain = (on) => commit((c) => patchCategory(c, cat.id, { brain: on }), on
    ? t("Catatan baharu {c} dihantar ke Otak AI mulai sapuan seterusnya. Catatan sedia ada tidak dihantar sendiri.", "New {c} posts go to the AI brain from the next sweep. Posts already here are not sent by themselves.", { c: cat.name })
    : t("Tidak lagi dihantar ke Otak AI.", "No longer sent to the AI brain."));

  const handlesInFeed = cat ? [...new Set(rowsFor(feed.rows, cat.id).map((r) => r.raw.owner || r.raw.handle))].sort((a, b) => a.localeCompare(b)) : [];
  const emptyWhy = !searched ? null : searched.authors === 0
    ? t("Carian terakhir tidak menemui catatan untuk kata carian ini.", "The last search found no posts for these search words.")
    : searched.judged === 0
      ? t("Carian terakhir menemui {a} penulis; semuanya sudah anda ikuti atau abaikan.", "The last search found {a} author(s); you already follow or dismissed every one.", { a: searched.authors })
      : t("Carian terakhir menemui {a} penulis ({k} sudah diikuti); bot menilai {j} dan tiada yang cukup mendalam.", "The last search found {a} author(s) ({k} already followed); the bot judged {j} and none showed enough depth.", { a: searched.authors, k: searched.known, j: searched.judged });

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6" data-expert-page>
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-accent"><GraduationCap size={15} /> {t("Kandungan pakar", "Expert content")}</p>
          <h1 className="mt-2 text-3xl leading-tight sm:text-4xl">{t("Belajar daripada yang pakar.", "Learn from the people who know.")}</h1>
          <p className="mt-2 hidden max-w-2xl text-sm text-muted sm:block">{t("Daftar akaun pakar mengikut bidang. Bot membaca catatan terbaharu mereka di Threads, Facebook dan Instagram, menyimpan catatan asal bersama ringkasannya, dan mencadangkan akaun lain yang patut diikuti. Jadikan mana-mana catatan sebagai idea.",
            "Register expert accounts by field. The bot reads their newest posts on Threads, Facebook and Instagram, keeps the original post beside its summary, and suggests other accounts worth following. Turn any post into an idea.")}</p>
          <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink/80" data-expert-status={light.light}>
            <SourceLight light={light.light} why={light.why} />
            <strong className="font-semibold text-ink">{t(LIGHT_NAME[light.light][0], LIGHT_NAME[light.light][1])}</strong>
            <span className="[overflow-wrap:anywhere]">{light.why}</span>
            {light.checked && <span className="tabular-nums text-ink/70">· {t("disemak", "checked")} {checkedText(light.checked, Date.now(), en)} MYT</span>}
          </p>
          {report?.stopped && (
            <p className="mt-1 text-xs text-ink/75" data-sweep-stopped>{report.stopped === "time"
              ? t("Sapuan terakhir berhenti kerana masa: {n} akaun belum dibaca dan didahulukan pada sapuan seterusnya.", "The last sweep stopped for time: {n} account(s) were not reached and go first at the next one.", { n: report.skipped || 0 })
              : t("Sapuan terakhir mencapai had halaman: {n} akaun belum dibaca dan didahulukan pada sapuan seterusnya.", "The last sweep reached its page budget: {n} account(s) were not reached and go first at the next one.", { n: report.skipped || 0 })}</p>
          )}
        </div>
        <Button variant="ghost" onClick={() => sweepNow()} disabled={waiting || !ready} data-expert-sweep>
          {waiting ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {waiting ? t("Menunggu pekerja…", "Waiting for the worker…") : t("Sapu sekarang", "Sweep now")}
        </Button>
      </motion.div>

      {!ready && (
        <p className="mb-5 flex gap-2 rounded-tile border border-warn/50 bg-warn/10 p-3 text-sm text-ink" role="status">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn" />
          {t("Segmen ini belum disediakan: jalankan supabase/082_expert_content.sql sekali. Selepas itu akaun boleh disimpan dan sapuan mula membaca.",
            "This segment is not set up yet: run supabase/082_expert_content.sql once. After that accounts can be saved and the sweep starts reading.")}
        </p>
      )}

      {/* the sub-segments: one per category, and the way to add another. One scrolling row on a phone, wrapped from sm up. */}
      <div role="tablist" aria-label={t("Kategori pakar", "Expert categories")} className="-mx-4 mb-3 flex flex-nowrap items-center gap-1.5 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0 [&::-webkit-scrollbar]:hidden [&>*]:shrink-0">
        {cfg.categories.map((c) => (
          <button type="button" key={c.id} role="tab" aria-selected={cat?.id === c.id} onClick={() => setCat(c.id)}
            className={`inline-flex min-h-[40px] items-center gap-2 rounded-pill px-4 py-2 text-sm font-medium transition ${cat?.id === c.id ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>
            {c.name}
            <span className={`rounded-pill px-1.5 text-[11px] tabular-nums ${cat?.id === c.id ? "bg-bg/20" : "bg-line/60"}`}>{counts[c.id] || 0}</span>
            {c.brain && <Brain size={12} aria-label={t("Dihantar ke Otak AI", "Sent to the AI brain")} />}
          </button>
        ))}
        {newCat === null ? (
          <button type="button" onClick={() => setNewCat("")} disabled={!ready} className="inline-flex min-h-[40px] items-center gap-1.5 rounded-pill border border-dashed border-line px-4 py-2 text-sm text-muted transition hover:border-accent hover:text-ink disabled:opacity-50" data-add-category>
            <Plus size={14} /> {t("Tambah kategori", "Add a category")}</button>
        ) : (
          <form onSubmit={createCategory} className="flex items-center gap-1.5">
            <Input autoFocus value={newCat} onChange={(e) => setNewCat(e.target.value)} maxLength={60} placeholder={t("cth. Pakar Kosmetik", "e.g. Cosmetic Expert")} className="!w-48 !py-1.5" aria-label={t("Nama kategori", "Category name")} />
            <Button size="sm" type="submit" disabled={busy}>{t("Tambah", "Add")}</Button>
            <button type="button" onClick={() => setNewCat(null)} aria-label={t("Batal", "Cancel")} className="grid h-9 w-9 place-items-center rounded-full text-muted hover:bg-surface-2 hover:text-ink"><X size={14} /></button>
          </form>
        )}
      </div>

      {!cat ? (
        <Card className="p-8 text-center text-sm text-muted">{t("Belum ada kategori. Tambah satu untuk mula.", "No category yet. Add one to start.")}</Card>
      ) : (
        <>
          {/* the open category's own bar: the AI brain switch where it can be seen, and on a phone the way into the account cards */}
          <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-tile bg-surface-2 px-3 py-2" data-category-bar>
            <button type="button" role="switch" aria-checked={cat.brain} disabled={busy || !ready} onClick={() => setBrain(!cat.brain)} data-brain-switch
              className="inline-flex min-h-[40px] items-center gap-2.5 text-left text-sm disabled:opacity-50">
              <span className={`relative h-6 w-11 shrink-0 rounded-full transition ${cat.brain ? "bg-accent" : "bg-line"}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface shadow-card transition-all ${cat.brain ? "left-[1.375rem]" : "left-0.5"}`} /></span>
              <span><strong className="font-semibold text-ink"><Brain size={13} className="mr-1 inline align-[-2px]" />{t("Hantar ke Otak AI", "Send to the AI brain")}</strong>
                <span className="ml-1.5 text-xs text-muted">{cat.brain ? t("hidup: catatan baharu jadi rujukan", "on: new posts become references") : t("mati", "off")}</span></span>
            </button>
            {cat.brain && unsent.length > 0 && (
              <button type="button" disabled={busy} onClick={sendExisting} data-send-existing className="inline-flex min-h-[36px] items-center gap-1.5 text-xs font-medium text-accent hover:underline disabled:opacity-50">
                {t("Hantar {n} catatan sedia ada", "Send the {n} post(s) already here", { n: Math.min(unsent.length, 40) })}</button>
            )}
            <button type="button" onClick={() => setManage((v) => !v)} aria-expanded={showManage} data-manage-toggle
              className="ml-auto inline-flex min-h-[40px] items-center gap-1.5 rounded-pill border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink lg:hidden">
              <Users size={13} /> {showManage ? t("Tutup urusan akaun", "Close accounts") : t("Urus akaun ({n})", "Manage accounts ({n})", { n: cat.handles.length })}
              {!showManage && suggestions.length > 0 && <span className="rounded-pill bg-accent/15 px-1.5 text-[10px] tabular-nums text-accent">+{suggestions.length}</span>}
            </button>
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,23rem)_minmax(0,1fr)] [&>*]:min-w-0">
            <div className={`space-y-4 ${showManage ? "" : "hidden"} lg:block`} data-manage>
              <Card className="p-4" data-expert-handles>
                <h2 className="flex items-center gap-2 text-base font-semibold"><UserPlus size={15} /> {t("Akaun diikuti", "Accounts followed")} <span className="text-xs font-normal text-muted">{cat.handles.length}/{MAX_HANDLES}</span></h2>
                <form onSubmit={register} className="mt-3 space-y-2.5">
                  <div>
                    <Label hint={t("nama akaun atau pautan profil", "account name or profile link")}>{t("Nama akaun", "Handle")}</Label>
                    <Input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@namaakaun" autoCapitalize="none" autoCorrect="off" spellCheck={false} data-handle-input />
                  </div>
                  <div>
                    <Label hint={t("pilih semua jika pemiliknya sama", "tick them all if the owner is the same")}>{t("Platform", "Platforms")}</Label>
                    <PlatformPicks value={plats} onChange={setPlats} disabled={busy} />
                  </div>
                  {plats.length > 0 && (
                    <div>
                      <Label hint={t("kosongkan jika sama dengan nama di atas", "leave empty if it is the name above")}>{t("Nama pengguna di setiap platform", "Username on each platform")}</Label>
                      <NameFields platforms={PLATFORMS.filter((p) => plats.includes(p))} names={names} main={handle} disabled={busy} onChange={(p, v) => setNames((n) => ({ ...n, [p]: v }))} />
                    </div>
                  )}
                  <Button type="submit" size="sm" disabled={busy || !ready || !handle.trim()} data-add-handle><Plus size={13} /> {t("Tambah akaun", "Add account")}</Button>
                </form>
                <ul className="mt-4 space-y-2">
                  {cat.handles.map((h) => (
                    <HandleRow key={h.handle} h={h} report={report} stats={stats[h.handle.toLowerCase()]} busy={busy}
                      active={who.toLowerCase() === h.handle.toLowerCase()}
                      onShow={(name) => { setWho(who.toLowerCase() === name.toLowerCase() ? "" : name); setManage(false); }}
                      onToggle={(name, p) => commit((c) => togglePlatform(c, cat.id, name, p))}
                      onName={(name, map) => commit((c) => setAccountNames(c, cat.id, name, map), t("Nama pengguna disimpan.", "Usernames saved."))}
                      onRemove={(name) => commit((c) => removeHandle(c, cat.id, name), t("@{h} dibuang.", "@{h} removed.", { h: name }))} />
                  ))}
                  {!cat.handles.length && <li className="rounded-tile border border-dashed border-line p-3 text-xs leading-relaxed text-muted">{t("Belum ada akaun. Tambah nama akaun pakar di atas, atau pilih daripada cadangan di bawah.", "No account yet. Add an expert's handle above, or pick one from the suggestions below.")}</li>}
                </ul>
                <p className="mt-3 text-[11px] leading-relaxed text-muted">{t("Threads dibaca tanpa log masuk. Facebook dan Instagram dibaca dengan log masuk tersimpan. Warna setiap platform ialah hasil sapuan terakhir; tekan nama akaun untuk melihat catatannya sahaja.",
                  "Threads is read without a login. Facebook and Instagram are read with the saved login. Each platform's colour is the last sweep's result; press an account's name to see only its posts.")}</p>
                {load.over && <p className="mt-2 flex gap-1.5 text-[11px] leading-relaxed text-warn"><AlertTriangle size={12} className="mt-0.5 shrink-0" />{t("Semua akaun bersama memerlukan {n} muatan halaman; satu sapuan membuka {m} (satu profil Instagram ialah 7). Akaun bergilir pada sapuan berikutnya.", "All accounts together need {n} page loads; one sweep opens {m} (an Instagram profile is 7). The accounts take turns at the following sweeps.", { n: load.loads, m: load.limit })}</p>}
              </Card>

              <Card className="p-4" data-expert-suggestions>
                <div className="flex items-center justify-between gap-2">
                  <h2 className="flex items-center gap-2 text-base font-semibold"><Sparkles size={15} /> {t("Patut diikuti", "Worth following")}</h2>
                  <button type="button" disabled={busy || !ready || !again.ok || !cat.keywords.length} onClick={searchAgain} data-search-again
                    title={again.ok ? t("Cari di Threads sekarang dengan kata carian kategori ini.", "Search Threads now with this category's search words.") : t("Boleh dicari semula dalam {n} minit.", "Can be searched again in {n} minute(s).", { n: again.waitMin })}
                    className="inline-flex min-h-[36px] items-center gap-1.5 rounded-pill border border-line px-3 py-1 text-xs font-medium text-ink transition hover:bg-surface-2 disabled:opacity-50">
                    <RefreshCw size={12} className={again.pending ? "animate-spin" : ""} /> {again.pending ? t("Sedang dicari…", "Searching…") : t("Cari semula", "Search again")}</button>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted">{t("Dicari sekali sehari di Threads dengan kata carian kategori ini, dan dinilai daripada catatan yang benar-benar dibaca. Tambah, dan nama itu hilang dari senarai.",
                  "Searched once a day on Threads with this category's search words, and judged on posts actually read. Add one and the name leaves the list.")}
                  {settings.expert_suggestions?.at && <span className="tabular-nums"> {t("Carian terakhir: {at} MYT.", "Last search: {at} MYT.", { at: checkedText(settings.expert_suggestions.at, Date.now(), en) })}</span>}</p>
                <ul className="mt-3 space-y-2">
                  {suggestions.map((s) => (
                    <li key={s.handle} className="rounded-tile border border-line/70 bg-bg/60 p-3" data-suggestion={s.handle}>
                      <div className="flex items-start justify-between gap-2">
                        <a href={profileUrl(s.platform || "threads", s.handle)} target="_blank" rel="noreferrer" className="min-w-0 truncate text-sm font-semibold text-ink hover:text-accent">@{s.handle} <ExternalLink size={11} className="inline align-baseline text-muted" /></a>
                        <span className="shrink-0 text-[10px] text-muted">{PLATFORM_NAMES[s.platform] || "Threads"}{s.posts ? ` · ${t("{n} catatan dibaca", "{n} post(s) read", { n: s.posts })}` : ""}</span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-ink/90 [overflow-wrap:anywhere]">{s.why}</p>
                      {s.sample && <p className="mt-1 line-clamp-2 border-l-2 border-line pl-2 text-[11px] italic leading-relaxed text-muted [overflow-wrap:anywhere]">{s.sample}</p>}
                      <div className="mt-2 flex gap-2">
                        <Button size="sm" disabled={busy} onClick={() => acceptSuggestion(s)}><Plus size={13} /> {t("Tambah", "Add")}</Button>
                        <Button size="sm" variant="ghost" disabled={busy} onClick={() => commit((c) => dismissSuggestion(c, cat.id, s.handle))}>{t("Abaikan", "Dismiss")}</Button>
                      </div>
                    </li>
                  ))}
                  {!suggestions.length && <li className="rounded-tile border border-dashed border-line p-3 text-xs leading-relaxed text-muted" data-suggestions-empty>{!cat.keywords.length
                    ? t("Isi kata carian dalam Tetapan kategori supaya bot tahu apa yang dicari.", "Fill in the search words in Category settings so the bot knows what to look for.")
                    : emptyWhy || t("Belum ada carian untuk kategori ini. Tekan Cari semula, atau tunggu sapuan seterusnya.", "No search has run for this category yet. Press Search again, or wait for the next sweep.")}</li>}
                </ul>
              </Card>

              {/* closed until wanted: set once. The AI brain switch is in the bar above, where it can be seen. */}
              <Card as="details" className="group p-4" data-expert-settings>
                <summary className="flex cursor-pointer list-none items-center gap-2 text-base font-semibold [&::-webkit-details-marker]:hidden"><Settings2 size={15} /> {t("Tetapan kategori", "Category settings")}
                  <span className="ml-auto text-xs font-normal text-muted"><span className="group-open:hidden">{t("buka", "open")}</span><span className="hidden group-open:inline">{t("tutup", "close")}</span></span></summary>
                <div className="mt-3 space-y-3">
                  <label className="block"><Label>{t("Nama kategori", "Category name")}</Label><Input value={form.name} maxLength={60} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} /></label>
                  <label className="block"><Label hint={t("bot menapis catatan dengan ini", "the bot filters posts by this")}>{t("Bidang", "Field")}</Label>
                    <TextArea rows={3} value={form.niche} maxLength={300} onChange={(e) => setForm((f) => ({ ...f, niche: e.target.value }))} placeholder={t("cth. keselamatan kosmetik, penilaian keselamatan, SCCS", "e.g. cosmetic safety, safety assessment, SCCS")} /></label>
                  <label className="block"><Label hint={t("sehingga 5, koma di antaranya", "up to 5, commas between")}>{t("Kata carian cadangan", "Search words for suggestions")}</Label>
                    <Input value={form.keywords} onChange={(e) => setForm((f) => ({ ...f, keywords: e.target.value }))} placeholder="AI agent, LLM" /></label>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <Button size="sm" disabled={busy || !dirty || !form.name.trim()} onClick={() => commit((c) => patchCategory(c, cat.id, form), t("Disimpan.", "Saved."))}>{t("Simpan", "Save")}</Button>
                    <button type="button" disabled={busy} onClick={dropCategory} className="inline-flex min-h-[36px] items-center gap-1.5 text-xs text-muted hover:text-danger disabled:opacity-50"><Trash2 size={13} /> {t("Padam kategori", "Delete category")}</button>
                  </div>
                </div>
              </Card>
            </div>

            <section aria-label={t("Catatan {c}", "{c} posts", { c: cat.name })} data-expert-feed>
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <label className="relative min-w-[12rem] flex-1">
                  <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
                  <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Cari dalam catatan…", "Search the posts…")} className="!pl-9" aria-label={t("Cari", "Search")} />
                </label>
                {handlesInFeed.length > 1 && (
                  <select value={who} onChange={(e) => setWho(e.target.value)} aria-label={t("Akaun", "Account")} className="rounded-pill border border-line bg-surface px-3 py-2 text-xs text-ink outline-none focus:border-accent">
                    <option value="">{t("Semua akaun", "All accounts")}</option>
                    {[...new Set([...handlesInFeed, ...(who ? [who] : [])])].map((h) => <option key={h} value={h}>@{h}</option>)}
                  </select>
                )}
                {who && (
                  <button type="button" onClick={() => setWho("")} data-clear-owner className="inline-flex min-h-[36px] items-center gap-1 rounded-pill bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
                    @{who} <X size={12} /></button>
                )}
                {hiddenN > 0 && <button type="button" onClick={() => setShowHidden((v) => !v)} className="inline-flex min-h-[36px] items-center gap-1.5 text-xs text-muted hover:text-ink">
                  {showHidden ? <EyeOff size={13} /> : <Eye size={13} />} {showHidden ? t("Sorok yang disembunyi", "Hide the hidden") : t("Tunjuk {n} disembunyi", "Show {n} hidden", { n: hiddenN })}</button>}
                <span className="ml-auto text-xs tabular-nums text-muted">{t("{n} catatan", "{n} post(s)", { n: rows.length })}</span>
              </div>
              {feed.error && !/semasa_watch/.test(feed.error) && <p className="mb-3 rounded-tile bg-danger/10 p-3 text-sm text-danger">{feed.error}</p>}
              {feed.loading ? (
                <div className="grid gap-4 xl:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-56" />)}</div>
              ) : rows.length ? (
                <motion.div variants={stagger} initial="hidden" animate="show" className="grid items-start gap-4 xl:grid-cols-2 [&>*]:min-w-0">
                  {rows.map((r) => <ExpertCard key={r.id} row={r} inBrain={Boolean(r.raw?.brain) || sent.has(r.id)} busy={busyId === r.id}
                    onIdea={onIdea} onBrain={toBrain} onHide={hide} />)}
                </motion.div>
              ) : (
                <Card className="p-8 text-center">
                  <GraduationCap size={28} className="mx-auto text-muted" />
                  <p className="mt-3 text-sm font-medium text-ink">{q || who ? t("Tiada catatan sepadan.", "No post matches.") : cat.handles.length ? t("Belum ada catatan untuk {c}.", "No posts for {c} yet.", { c: cat.name }) : t("Tambah akaun pertama untuk {c}.", "Add the first account for {c}.", { c: cat.name })}</p>
                  {!q && !who && <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">{cat.handles.length
                    ? t("Sapuan berjalan dua kali sehari (05:10 dan 17:10 MYT) dan membaca catatan 14 hari terakhir. Tekan Sapu sekarang untuk mula.", "The sweep runs twice a day (05:10 and 17:10 MYT) and reads the last 14 days of posts. Press Sweep now to start.")
                    : t("Daftar nama akaun dalam kad Akaun diikuti dan pilih platformnya. Bot membaca, meringkas dan menyimpan catatan asalnya di sini.", "Register a handle in the Accounts followed card and tick its platforms. The bot reads, summarises and keeps the original post here.")}</p>}
                  {who && stats[who.toLowerCase()]?.off > 0 && <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-muted">{t("{n} catatan akaun ini dibaca dan dinilai di luar bidang kategori.", "{n} of this account's posts were read and judged off the category's field.", { n: stats[who.toLowerCase()].off })}</p>}
                  {cat.brain && <Button size="sm" variant="ghost" className="mt-4" onClick={() => go("otak")}><Brain size={13} /> {t("Buka Otak AI", "Open the AI brain")}</Button>}
                </Card>
              )}
            </section>
          </div>
        </>
      )}
    </main>
  );
}

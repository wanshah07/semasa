import { useState } from "react";
import { Briefcase, Globe, Loader2, Plus, Trash2 } from "lucide-react";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { TABLES } from "../lib/SupabaseClient";
import { MAX_PAGES, MAX_POSTS, MAX_SITES, cleanPages, cleanPosts, cleanSites, linkedinKind, linkedinOf, refused, sitesOf, webUrl, withLinkedin, withSites } from "../lib/linkSources";
import Button from "../components/ui/Button";
import { Input, Label, TextArea } from "../components/ui/Field";
import WatchSegment from "../components/WatchSegment";
import { useView } from "../components/ViewToggle";

/* Sumber LinkedIn / LinkedIn sources (Wan, 16 Nov 2026: "add segment in linkedn that I can add url website to scrape such
   as https://lom.agc.gov.my/index.php" and "for linkedn ... scrape also from linkedns based on recent case, and big
   impression"; he chose pasted links plus watched pages, with no account).

   Two lists and the feed each one fills:
     Laman web   pages that list what is new. The sweep reads each twice a day and shows the links not seen before.
     LinkedIn    post links he pasted (always shown) and company pages to watch (only recent posts with many reactions).
   The page saves the two lists into the settings row `sources`, beside the Threads, Facebook and Instagram ones, and nothing
   else; the reading is done by the Sources sweep (backend/semasa/own_links.py). Every row has "Jadikan idea", which opens the
   idea composer on the LinkedIn stream.

   LinkedIn shows a visitor who is not signed in a post's own page and a company page's recent posts, but not a person's
   profile. So a personal profile cannot be watched, and the page says so the moment one is pasted. */

const MIGRATION = ["Jalankan supabase/083_linkedin_sources.sql sekali dahulu.", "Run supabase/083_linkedin_sources.sql once first."];

function UrlList({ items, setItems, max, placeholder, addLabel, check, onToast, t }) {
  const [next, setNext] = useState("");
  function add() {
    const [ok, why] = check(next);
    if (!ok) return onToast(why, "warn");
    if (items.includes(ok)) return onToast(t("Pautan itu sudah ada.", "That link is already there."), "warn");
    if (items.length >= max) return onToast(t("Paling banyak {n}.", "At most {n}.", { n: max }), "warn");
    setItems([...items, ok]); setNext("");
  }
  return (
    <>
      <ul className="mt-2 space-y-1.5">
        {items.map((u) => (
          <li key={u} className="flex items-center gap-2">
            <a href={u} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-ink hover:underline">{u.replace(/^https?:\/\/(www\.)?/, "")}</a>
            <button type="button" onClick={() => setItems(items.filter((x) => x !== u))} aria-label={t("Buang pautan", "Remove link")}
              className="shrink-0 rounded-pill p-2 text-muted hover:text-danger"><Trash2 size={14} /></button>
          </li>
        ))}
        {items.length === 0 && <li className="text-xs text-muted">{t("Belum ada.", "None yet.")}</li>}
      </ul>
      <div className="mt-2 flex items-center gap-2">
        <Input value={next} onChange={(e) => setNext(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder} aria-label={addLabel} className="min-w-0 flex-1" inputMode="url" />
        <Button type="button" size="sm" variant="soft" onClick={add} disabled={!next.trim()}><Plus size={13} /> {t("Tambah", "Add")}</Button>
      </div>
    </>
  );
}

function Websites({ setting, saveSetting, onToast }) {
  const { t } = useLang();
  const saved = sitesOf(setting);
  const [sites, setSites] = useState(saved);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(sites) !== JSON.stringify(saved);
  const check = (raw) => { const u = webUrl(raw); return u ? [u, ""] : ["", t("Tulis alamat penuh, bermula dengan https://", "Type the whole address, starting with https://")]; };
  async function save() {
    setBusy(true);
    try {
      await saveSetting("sources", withSites(setting, sites));
      onToast(t("Disimpan. Sapuan seterusnya membaca laman ini.", "Saved. The next sweep reads these pages."), "ok");
    } catch (e) { onToast(e.message, "danger"); } finally { setBusy(false); }
  }
  return (
    <section className="rounded-card border border-line bg-surface p-3 shadow-card sm:p-4" data-link-list="website">
      <h2 className="text-sm font-medium">{t("Laman web untuk dibaca", "Websites to read")} <span className="text-[11px] font-normal text-muted">· {saved.length}/{MAX_SITES}</span></h2>
      <p className="mt-1 text-[11px] text-muted">{t("Letak halaman yang menyenaraikan perkara baharu (contoh: https://lom.agc.gov.my/index.php). Dua kali sehari Semasa membaca halaman itu dan menunjukkan pautan yang belum pernah dilihat. AI menulis ringkasan dan menyembunyikan yang tidak berkaitan.",
        "Add a page that lists what is new (for example https://lom.agc.gov.my/index.php). Twice a day Semasa reads it and shows the links it has not seen before. AI writes a summary and hides what is not relevant.")}</p>
      <UrlList items={sites} setItems={setSites} max={MAX_SITES} check={check} onToast={onToast} t={t}
        placeholder="https://lom.agc.gov.my/index.php" addLabel={t("Alamat laman web", "Website address")} />
      <div className="mt-3 flex items-center gap-2">
        <Button type="button" size="sm" onClick={save} disabled={!dirty || busy}>{busy && <Loader2 size={13} className="animate-spin" />} {t("Simpan", "Save")}</Button>
        {dirty && <span className="text-[11px] text-muted">{t("Belum disimpan.", "Not saved yet.")}</span>}
      </div>
    </section>
  );
}

function LinkedInLists({ setting, saveSetting, onToast }) {
  const { t } = useLang();
  const saved = linkedinOf(setting);
  const [posts, setPosts] = useState(saved.posts);
  const [pages, setPages] = useState(saved.pages);
  const [floor, setFloor] = useState(String(saved.min_reactions));
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify([posts, pages, Math.max(0, Math.round(Number(floor) || 0))]) !== JSON.stringify([saved.posts, saved.pages, saved.min_reactions]);
  const profileMsg = t("Itu profil peribadi. LinkedIn hanya menunjukkan post profil peribadi selepas log masuk, jadi ia tidak boleh dipantau. Tampal pautan post orang itu satu per satu.",
    "That is a personal profile. LinkedIn shows a person's posts only after sign-in, so it cannot be watched. Paste that person's post links one by one instead.");
  const checkPage = (raw) => { const [k, u] = linkedinKind(raw); return k === "page" ? [u, ""] : ["", k === "profile" ? profileMsg : t("Tulis alamat halaman syarikat, contohnya https://www.linkedin.com/company/nama/", "Type a company page address, for example https://www.linkedin.com/company/name/")]; };
  function addPasted() {
    const found = cleanPosts(paste), bad = refused(paste, "post");
    if (!found.length) return onToast(bad.profiles ? profileMsg : t("Tiada pautan post LinkedIn di situ. Guna “Copy link to post” pada post itu.", "No LinkedIn post link in there. Use “Copy link to post” on the post."), "warn");
    const next = cleanPosts([...posts, ...found]);
    setPosts(next); setPaste("");
    if (bad.profiles || bad.other) onToast(t("{n} pautan ditambah; {m} bukan pautan post dan ditinggalkan.", "{n} link(s) added; {m} were not post links and were left out.", { n: next.length - posts.length, m: bad.profiles + bad.other }), "info");
  }
  async function save() {
    setBusy(true);
    try {
      await saveSetting("sources", withLinkedin(setting, { posts, pages, min_reactions: floor }));
      onToast(t("Disimpan. Sapuan seterusnya membaca senarai ini.", "Saved. The next sweep reads these lists."), "ok");
    } catch (e) { onToast(e.message, "danger"); } finally { setBusy(false); }
  }
  return (
    <section className="rounded-card border border-line bg-surface p-3 shadow-card sm:p-4" data-link-list="linkedin">
      <h2 className="text-sm font-medium">{t("Post LinkedIn yang anda tampal", "LinkedIn posts you pasted")} <span className="text-[11px] font-normal text-muted">· {saved.posts.length}/{MAX_POSTS}</span></h2>
      <p className="mt-1 text-[11px] text-muted">{t("Tampal pautan post (boleh banyak sekali gus). Setiap satu dibaca tanpa log masuk: teksnya, penulisnya dan bilangan reaksi. Ia sentiasa ditunjukkan.",
        "Paste post links (several at once is fine). Each is read without signing in: its text, its author and its reaction count. A pasted post is always shown.")}</p>
      <TextArea rows={2} value={paste} onChange={(e) => setPaste(e.target.value)} className="mt-2" aria-label={t("Pautan post LinkedIn", "LinkedIn post links")}
        placeholder="https://www.linkedin.com/posts/…" />
      <div className="mt-2"><Button type="button" size="sm" variant="soft" onClick={addPasted} disabled={!paste.trim()}><Plus size={13} /> {t("Tambah pautan", "Add links")}</Button></div>
      <ul className="mt-2 space-y-1.5">
        {posts.map((u) => (
          <li key={u} className="flex items-center gap-2">
            <a href={u} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-ink hover:underline">{u.replace("https://www.linkedin.com/posts/", "")}</a>
            <button type="button" onClick={() => setPosts(posts.filter((x) => x !== u))} aria-label={t("Buang pautan", "Remove link")} className="shrink-0 rounded-pill p-2 text-muted hover:text-danger"><Trash2 size={14} /></button>
          </li>
        ))}
      </ul>

      <h2 className="mt-5 text-sm font-medium">{t("Halaman syarikat untuk dipantau", "Company pages to watch")} <span className="text-[11px] font-normal text-muted">· {saved.pages.length}/{MAX_PAGES}</span></h2>
      <p className="mt-1 text-[11px] text-muted">{t("Halaman syarikat, sekolah atau showcase sahaja. Daripada post 30 hari terakhir, hanya yang cukup reaksi ditunjukkan, paling ramai dahulu.",
        "Company, school or showcase pages only. Of the last 30 days' posts, only those with enough reactions are shown, loudest first.")}</p>
      <UrlList items={pages} setItems={setPages} max={MAX_PAGES} check={checkPage} onToast={onToast} t={t}
        placeholder="https://www.linkedin.com/company/…" addLabel={t("Alamat halaman syarikat", "Company page address")} />
      <label className="mt-3 block max-w-[220px]"><Label>{t("Reaksi paling sedikit", "Fewest reactions")}</Label>
        <Input type="number" min="0" inputMode="numeric" value={floor} onChange={(e) => setFloor(e.target.value)} aria-label={t("Reaksi paling sedikit", "Fewest reactions")} /></label>
      <div className="mt-3 flex items-center gap-2">
        <Button type="button" size="sm" onClick={save} disabled={!dirty || busy}>{busy && <Loader2 size={13} className="animate-spin" />} {t("Simpan", "Save")}</Button>
        {dirty && <span className="text-[11px] text-muted">{t("Belum disimpan.", "Not saved yet.")}</span>}
      </div>
    </section>
  );
}

export default function LinkedInSourcesTab({ settings, save, brand, user, onToast, onIdea }) {
  const { t } = useLang();
  const [segRaw, setSeg] = useView("li-sumber.segment", "website");
  const seg = segRaw === "linkedin" ? "linkedin" : "website";
  const watch = useTable(TABLES.watch, { limit: 300, realtime: false, everyMs: 120_000, eq: ["section", seg] });
  const needs = /section_check|check constraint/i.test(watch.error || "") || /083_linkedin_sources/.test(JSON.stringify(settings.sources?.report || {}));
  const tabs = [["website", t("Laman web", "Websites"), Globe], ["linkedin", "LinkedIn", Briefcase]];
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-8 sm:px-6">
      <p className="text-[13px] font-semibold text-accent">LinkedIn</p>
      <h1 className="mt-1 text-3xl leading-tight sm:text-4xl">{t("Sumber untuk idea LinkedIn", "Sources for LinkedIn ideas")}</h1>
      <p className="mt-2 max-w-2xl text-sm text-muted">{t("Dua senarai anda sendiri: laman web yang menyenaraikan perkara baharu, dan post LinkedIn yang ramai orang beri reaksi. Setiap baris boleh dijadikan idea LinkedIn. Pautan sumber tidak pernah masuk ke dalam post.",
        "Two lists of your own: websites that list what is new, and LinkedIn posts many people reacted to. Any row can become a LinkedIn idea. A source's link never reaches a post.")}</p>
      {needs && <p className="mt-3 rounded-card border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-ink">{t(MIGRATION[0], MIGRATION[1])}</p>}
      <div className="mt-5 flex flex-wrap gap-2" role="tablist" aria-label={t("Senarai sumber", "Source lists")}>
        {tabs.map(([k, label, Icon]) => (
          <button key={k} type="button" role="tab" aria-selected={seg === k} onClick={() => setSeg(k)}
            className={`inline-flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-[13px] font-medium ${seg === k ? "border-accent bg-accent/10 text-accent" : "border-line text-muted hover:text-ink"}`}>
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {seg === "website"
          ? <Websites key={JSON.stringify(sitesOf(settings.sources))} setting={settings.sources} saveSetting={save} onToast={onToast} />
          : <LinkedInLists key={JSON.stringify(linkedinOf(settings.sources))} setting={settings.sources} saveSetting={save} onToast={onToast} />}
      </div>
      <WatchSegment key={seg} section={seg} watch={watch} setting={settings.sources} saveSetting={save} brand={brand} user={user} onIdea={onIdea} onToast={onToast} />
    </main>
  );
}

import { useEffect, useState } from "react";
import { Eye, FlaskConical, ImagePlus, KeyRound, Lock, Plus, Save, ScrollText, Trash2 } from "lucide-react";
import { dayNames } from "../lib/brand";
import { faqCategories } from "../lib/faqExport";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { BUILT_IN_INDO } from "../lib/compliance";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Select } from "../components/ui/Field";

const SLOT = /^([01]\d|2[0-3]):[0-5]\d$/;
const parseSlots = (s) => [...new Set(s.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean))].sort();

/* Studio's Settings, the parts Semasa uses now: posting positions and the weekly rota.
   The publishing switch is shown, never editable: the database refuses it from the browser. */
export default function SettingsTab({ settings, brand, save, onToast }) {
  const { t } = useLang();
  const days = dayNames();
  const [regSlots, setRegSlots] = useState("");
  const [liSlots, setLiSlots] = useState("");
  const [liDays, setLiDays] = useState([]);
  const [rota, setRota] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRegSlots((brand.regulab.slots || []).join(", "));
    setLiSlots((brand.linkedin.slots || []).join(", "));
    setLiDays(brand.linkedin.days || []);
    setRota(Object.fromEntries([0, 1, 2, 3, 4, 5, 6].map((d) => [d, [...((brand.regulab.schedule || {})[d] || [])]])));
  }, [JSON.stringify(brand)]); // eslint-disable-line react-hooks/exhaustive-deps -- only when the slots and rota themselves change

  const domains = Object.entries(brand.regulab.domains || {});
  const publishing = settings.publishing || {};

  function toggle(day, dom) {
    setRota((r) => ({ ...r, [day]: r[day].includes(dom) ? r[day].filter((x) => x !== dom) : [...r[day], dom] }));
  }

  async function submit() {
    const rs = parseSlots(regSlots), ls = parseSlots(liSlots);
    const bad = [...rs, ...ls].filter((x) => !SLOT.test(x));
    if (bad.length) return onToast(t("Masa tidak sah: {bad} (guna HH:MM)", "Invalid time: {bad} (use HH:MM)", { bad: bad.join(", ") }), "warn");
    if (!rs.length || !ls.length) return onToast(t("Setiap aliran perlukan sekurang-kurangnya satu slot.", "Each stream needs at least one slot."), "warn");
    const current = settings.brand || {};
    const next = {
      ...current,
      regulab: { ...(current.regulab || {}), slots: rs,
        schedule: Object.fromEntries(Object.entries(rota).map(([d, list]) => [String(d), list])) },
      linkedin: { ...(current.linkedin || {}), slots: ls, days: [...liDays].sort() },
    };
    setBusy(true);
    try { await save("brand", next); onToast(t("Tetapan disimpan.", "Settings saved."), "ok"); } catch (e) { onToast(e.message, "danger"); }
    setBusy(false);
  }

  return (
    <main className="mx-auto max-w-page space-y-5 px-4 pb-20 pt-10 sm:px-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Tetapan", "Settings")}</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Slot dan giliran mingguan.", "Slots and the weekly rota.")}</h1>
      </div>

      <Card className="flex items-start gap-3 p-5">
        <Lock size={18} className={publishing.enabled ? "text-ok" : "text-warn"} />
        <div>
          <h3 className="text-lg">{t("Penerbitan", "Publishing")}: {publishing.enabled ? t("HIDUP", "ON") : t("MATI", "OFF")}</h3>
          <p className="mt-1 text-sm text-muted">{publishing.why || ""}</p>
          <p className="mt-1 text-[12px] text-muted">{t("Suis ini tidak boleh diubah dari laman ini. Ia diubah di Supabase SQL editor sahaja.", "This switch cannot be changed from this page. It is changed in the Supabase SQL editor only.")}</p>
        </div>
      </Card>

      <AiSettings onToast={onToast} github={{ scrape: settings.ai_github_scrape, media: settings.ai_github_media }} />

      <MireldTrial settings={settings} save={save} onToast={onToast} />

      <Card className="grid gap-4 p-5 sm:grid-cols-2">
        <label className="block"><Label hint={t("HH:MM, dipisah koma", "HH:MM, comma-separated")}>{t("Slot ws.regulab (MYT)", "ws.regulab slots (MYT)")}</Label>
          <Input value={regSlots} onChange={(e) => setRegSlots(e.target.value)} /></label>
        <label className="block"><Label hint={t("HH:MM, dipisah koma", "HH:MM, comma-separated")}>{t("Slot LinkedIn (MYT)", "LinkedIn slots (MYT)")}</Label>
          <Input value={liSlots} onChange={(e) => setLiSlots(e.target.value)} /></label>
        <div className="sm:col-span-2">
          <Label>{t("Hari LinkedIn", "LinkedIn days")}</Label>
          <div className="flex flex-wrap gap-3 text-sm">
            {days.map((n, d) => (
              <label key={d} className="flex items-center gap-1.5">
                <input type="checkbox" checked={liDays.includes(d)}
                  onChange={() => setLiDays((x) => (x.includes(d) ? x.filter((y) => y !== d) : [...x, d]))} /> {n}
              </label>
            ))}
          </div>
        </div>
      </Card>

      <Card className="overflow-x-auto p-5">
        <Label hint={t("hari tanpa domain = tiada post ws.regulab", "a day with no domain = no ws.regulab post")}>{t("Giliran ws.regulab", "ws.regulab rota")}</Label>
        <table className="mt-2 w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr><th className="py-1 pr-2 font-medium text-muted">{t("Hari", "Day")}</th>
              {domains.map(([k, l]) => <th key={k} className="px-1 py-1 font-medium text-muted" title={l}>{k}</th>)}</tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4, 5, 6, 0].map((d) => (
              <tr key={d} className="border-t border-line/70">
                <td className="py-1.5 pr-2">{days[d]}</td>
                {domains.map(([k]) => (
                  <td key={k} className="px-1 py-1.5">
                    <input type="checkbox" aria-label={`${days[d]} ${k}`} checked={(rota[d] || []).includes(k)} onChange={() => toggle(d, k)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Button onClick={submit} disabled={busy}><Save size={14} /> {t("Simpan tetapan", "Save settings")}</Button>

      <WriterSettings settings={settings} save={save} onToast={onToast} />

      <IndoTabung settings={settings} save={save} onToast={onToast} />

      <FaqCategories settings={settings} save={save} onToast={onToast} />
    </main>
  );
}

const lines = (v) => (Array.isArray(v) ? v : []).join("\n");
const listOf = (s) => [...new Set(String(s || "").split("\n").map((x) => x.trim()).filter(Boolean))];
const tagsOf = (s) => [...new Set(String(s || "").split(/[\s,]+/).map((x) => x.trim()).filter(Boolean)
  .map((x) => (x.startsWith("#") ? x : `#${x}`)))];

/* Studio's writer settings (supabase/021 seeded them from Studio itself): the voice each stream writes in, what it must
   never write, its hashtags and the fatwa gazette line. Every writer in the worker reads them (ideas.writer_block);
   they add to the rules and can never lift one, so nothing typed here can switch a check off. */
function WriterSettings({ settings, save, onToast }) {
  const { t } = useLang();
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const w = settings.writer;
  useEffect(() => {
    const r = w?.regulab || {}, l = w?.linkedin || {};
    setF({ rVoice: r.voice || "", rNever: lines(r.never), rCore: (r.hashtags_core || []).join(" "), rRot: (r.hashtags_rotate || []).join(" "),
      rFatwa: r.fatwa_warning || "", lVoice: l.voice || "", lNever: lines(l.never), lTags: (l.hashtags || []).join(" ") });
  }, [JSON.stringify(w)]); // eslint-disable-line react-hooks/exhaustive-deps -- a change elsewhere must not wipe an edit here
  if (!f) return null;
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));

  async function submit() {
    const next = {
      ...(w || {}),
      regulab: { ...((w || {}).regulab || {}), voice: f.rVoice.trim(), never: listOf(f.rNever), hashtags_core: tagsOf(f.rCore),
        hashtags_rotate: tagsOf(f.rRot), fatwa_warning: f.rFatwa.trim() },
      linkedin: { ...((w || {}).linkedin || {}), voice: f.lVoice.trim(), never: listOf(f.lNever), hashtags: tagsOf(f.lTags) },
    };
    setBusy(true);
    try { await save("writer", next); onToast(t("Gaya penulisan disimpan. Draf seterusnya ikut ini.", "Writing style saved. The next drafts follow it."), "ok"); } catch (e) {
      onToast(/0 rows/.test(e.message) ? t("Jalankan supabase/021_studio_workflow.sql dahulu.", "Run supabase/021_studio_workflow.sql first.") : e.message, "danger");
    }
    setBusy(false);
  }

  const area = (k, rows = 3, ph = "") => <textarea value={f[k]} onChange={set(k)} rows={rows} placeholder={ph}
    className="w-full resize-y rounded-tile border border-line bg-bg p-2 text-[13px] outline-none focus:border-accent" />;
  const pillars = Object.entries(w?.regulab?.pillars || {});
  return (
    <Card className="p-5">
      <h2 className="flex items-center gap-2 text-lg"><ScrollText size={16} /> {t("Gaya penulisan", "Writing style")}</h2>
      <p className="mt-1 text-[12px] text-muted">{t("Dibaca oleh setiap penulis bot. Ia menambah pada peraturan, tidak pernah menarik balik mana-mana semakan.",
        "Read by every writer in the bot. It adds to the rules and never switches a check off.")}</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="space-y-2">
          <p className="text-sm font-medium">ws.regulab</p>
          <label className="block"><Label>{t("Suara", "Voice")}</Label>{area("rVoice", 4)}</label>
          <label className="block"><Label hint={t("satu baris satu", "one per line")}>{t("Jangan sekali-kali", "Never")}</Label>{area("rNever", 6)}</label>
          <label className="block"><Label hint={t("sentiasa", "always")}>{t("Hashtag teras", "Core hashtags")}</Label><Input value={f.rCore} onChange={set("rCore")} /></label>
          <label className="block"><Label hint={t("satu atau dua ikut cerita", "one or two as the story fits")}>{t("Hashtag bergilir", "Rotating hashtags")}</Label><Input value={f.rRot} onChange={set("rRot")} /></label>
          <label className="block"><Label hint={t("ayat tepat dalam setiap post fatwa", "the exact line in every fatwa post")}>{t("Amaran fatwa", "Fatwa line")}</Label>{area("rFatwa", 2)}</label>
          {pillars.length > 0 && <p className="text-[11.5px] text-muted">{t("Tiang (dari Studio): ", "Pillars (from Studio): ")}
            {pillars.map(([d, ps]) => `${d}: ${(ps || []).join(", ")}`).join(" · ")}</p>}
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">LinkedIn</p>
          <label className="block"><Label>{t("Suara", "Voice")}</Label>{area("lVoice", 4)}</label>
          <label className="block"><Label hint={t("satu baris satu", "one per line")}>{t("Jangan sekali-kali", "Never")}</Label>{area("lNever", 6)}</label>
          <label className="block"><Label hint={t("pilihan", "optional")}>Hashtag</Label><Input value={f.lTags} onChange={set("lTags")} /></label>
        </div>
      </div>
      <Button className="mt-4" onClick={submit} disabled={busy}><Save size={14} /> {t("Simpan gaya penulisan", "Save writing style")}</Button>
    </Card>
  );
}

const keyOf = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 30);

/* The FAQ categories the AI chooses from, and the chips in the FAQ tab. "lain" (Other) always stays:
   it is where anything that fits nowhere else goes. */
function FaqCategories({ settings, save, onToast }) {
  const { t, lang } = useLang();
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setRows(faqCategories(settings).map((c) => ({ ...c, subs: c.subs.join(", "), fresh: false })));
  }, [JSON.stringify(settings.faq?.categories)]); // eslint-disable-line react-hooks/exhaustive-deps -- a change elsewhere must not wipe an edit here
  const set = (i, k, v) => setRows((r) => r.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  async function submit() {
    const cats = rows.map((r) => {
      const subs = [...new Set(r.subs.split(",").map((x) => x.trim()).filter(Boolean))];
      const c = { key: r.fresh ? keyOf(r.key || r.bm) : r.key, bm: r.bm.trim(), en: (r.en || r.bm).trim(), subs };
      if (r.auto) Object.assign(c, { auto: true, auto_at: r.auto_at || null });
      const autoSubs = (r.auto_subs || []).filter((x) => subs.includes(x));
      if (autoSubs.length) c.auto_subs = autoSubs;
      return c;
    });
    if (cats.some((c) => !c.key || !c.bm)) return onToast(t("Setiap kategori perlukan nama BM.", "Each category needs a BM name."), "warn");
    const keys = cats.map((c) => c.key);
    if (new Set(keys).size !== keys.length) return onToast(t("Dua kategori mempunyai kunci yang sama.", "Two categories have the same key."), "warn");
    setBusy(true);
    try {
      // what Wan removed from the bot's own additions, the bot never adds again (semasa/faq_sort.py)
      const before = faqCategories(settings);
      const kept = new Set(cats.map((c) => c.key));
      const declined = new Set((settings.faq?.declined || []).map(String));
      for (const c of before) {
        if (c.auto && !kept.has(c.key)) declined.add(c.bm);
        const now = cats.find((x) => x.key === c.key);
        for (const sub of c.auto_subs || []) if (!now || !now.subs.includes(sub)) declined.add(sub);
      }
      // the bot may have added to the list since this page loaded it: keep those additions, don't erase them unseen
      const { data: live } = await supabase.from(TABLES.settings).select("value").eq("key", "faq").maybeSingle();
      const liveValue = live?.value && typeof live.value === "object" ? live.value : (settings.faq || {});
      const known = new Set(before.map((c) => c.key));
      const knownSubs = Object.fromEntries(before.map((c) => [c.key, new Set(c.subs)]));
      const merged = [...cats];
      for (const c of faqCategories({ faq: liveValue })) {
        if (c.auto && !known.has(c.key) && !merged.some((x) => x.key === c.key)) {
          merged.splice(Math.max(0, merged.findIndex((x) => x.key === "lain")), 0, c);
        }
        const mine = merged.find((x) => x.key === c.key);
        for (const sub of c.auto_subs || []) {
          if (mine && known.has(c.key) && !knownSubs[c.key].has(sub) && !mine.subs.includes(sub)) {
            mine.subs = [...mine.subs, sub]; mine.auto_subs = [...(mine.auto_subs || []), sub];
          }
        }
      }
      for (const d of liveValue.declined || []) declined.add(String(d));
      await save("faq", { ...liveValue, categories: merged, declined: [...declined], changed_at: new Date().toISOString() });
      onToast(t("Kategori FAQ disimpan.", "FAQ categories saved."), "ok");
    } catch (e) {
      onToast(/0 rows|faq/i.test(e.message) ? t("Jalankan supabase/007_faq.sql dahulu.", "Run supabase/007_faq.sql first.") : e.message, "danger");
    }
    setBusy(false);
  }

  return (
    <Card className="space-y-3 p-5">
      <div>
        <h3 className="text-lg">{t("Kategori FAQ", "FAQ categories")}</h3>
        <p className="mt-1 text-[12px] text-muted">{lang === "en" ? (<>The AI picks one category and one subcategory from this list. Subcategories are separated by commas.
          The bot can also add categories (when at least 2 questions fit one) and subcategories of its own, marked
          <b> ✦ made by the bot</b>, and re-sorts the questions in Other whenever this list changes. A bot category or
          subcategory you remove is never made again. Questions you placed yourself are never moved.</>) : (<>AI memilih satu kategori dan satu subkategori daripada senarai ini. Subkategori dipisah dengan koma.
          Bot juga boleh menambah kategori (bila sekurang-kurangnya 2 soalan sesuai dengannya) dan subkategori sendiri, ditanda
          <b> ✦ dicipta bot</b>, dan menyusun semula soalan dalam Lain-lain setiap kali senarai ini berubah. Kategori atau
          subkategori bot yang anda buang tidak akan dicipta semula. Soalan yang anda letak sendiri tidak akan dialih.</>)}</p>
      </div>
      {rows.map((r, i) => (
        <div key={i} className="grid gap-2 rounded-tile bg-surface-2/60 p-2.5 sm:grid-cols-[1fr_1fr_2fr_auto]">
          {(r.auto || (r.auto_subs || []).length > 0) && (
            <p className="text-[10px] text-accent sm:col-span-4">✦ {r.auto ? t("Kategori dicipta bot", "Category made by the bot") : t("Subkategori dicipta bot", "Subcategory made by the bot")}
              {(r.auto_subs || []).length > 0 && `: ${r.auto_subs.join(", ")}`}</p>
          )}
          <Input value={r.bm} onChange={(e) => set(i, "bm", e.target.value)} placeholder={t("Nama (BM)", "Name (BM)")} aria-label={t("Nama kategori BM", "Category name (BM)")} />
          <Input value={r.en} onChange={(e) => set(i, "en", e.target.value)} placeholder="Name (EN)" aria-label={t("Nama kategori EN", "Category name (EN)")} />
          <Input value={r.subs} onChange={(e) => set(i, "subs", e.target.value)} placeholder={t("Subkategori, dipisah koma", "Subcategories, comma-separated")} aria-label={t("Subkategori", "Subcategories")} />
          {r.key === "lain" ? <span className="self-center px-2 text-[11px] text-muted">{t("tetap", "fixed")}</span> : (
            <button type="button" aria-label={t("Buang kategori", "Remove category")} onClick={() => setRows((x) => x.filter((_, j) => j !== i))}
              className="self-center rounded p-1 text-muted hover:text-danger"><Trash2 size={14} /></button>
          )}
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" size="sm" onClick={() => setRows((x) => [...x.filter((c) => c.key !== "lain"),
          { key: "", bm: "", en: "", subs: "", fresh: true }, ...x.filter((c) => c.key === "lain")])}><Plus size={12} /> {t("Tambah kategori", "Add category")}</Button>
        <Button size="sm" onClick={submit} disabled={busy}><Save size={12} /> {t("Simpan kategori FAQ", "Save FAQ categories")}</Button>
      </div>
    </Card>
  );
}

/* Wan's tabung: Indonesian words the writers still slip in. Every writer is told to avoid them, and the
   compliance check blocks them in captions and slides, exactly like the built-in list. */
function IndoTabung({ settings, save, onToast }) {
  const { t } = useLang();
  const [rows, setRows] = useState([]);
  const [indo, setIndo] = useState("");
  const [bm, setBm] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const list = settings.bahasa?.indo;
    setRows(Array.isArray(list) ? list.map((e) => (typeof e === "string" ? { indo: e, bm: "" } : { indo: e.indo || "", bm: e.bm || "" })) : []);
  }, [JSON.stringify(settings.bahasa?.indo)]); // eslint-disable-line react-hooks/exhaustive-deps

  async function persist(next, msg) {
    setBusy(true);
    let ok = false;
    try { await save("bahasa", { ...(settings.bahasa || {}), indo: next }); setRows(next); onToast(msg, "ok"); ok = true; } catch (e) {
      onToast(/0 rows/.test(e.message) ? t("Jalankan supabase/007_faq.sql dahulu (ia menyediakan tabung ini).", "Run supabase/007_faq.sql first (it sets up this list).") : e.message, "danger");
    }
    setBusy(false);
    return ok;
  }
  async function add(e) {
    e.preventDefault();
    const w = indo.replace(/\s+/g, " ").trim().toLowerCase();
    if (!w) return;
    if (BUILT_IN_INDO.includes(w)) return onToast(t('"{w}" sudah dalam senarai terbina.', '"{w}" is already in the built-in list.', { w }), "info");
    if (rows.some((r) => r.indo.toLowerCase() === w)) return onToast(t('"{w}" sudah ada dalam tabung.', '"{w}" is already in the list.', { w }), "info");
    // the words stay in the boxes when the save fails, so nothing typed is lost
    if (await persist([...rows, { indo: w, bm: bm.trim() }], t('"{w}" ditambah. Semua penulis AI akan mengelaknya.', '"{w}" added. Every AI writer will avoid it.', { w }))) {
      setIndo(""); setBm("");
    }
  }

  return (
    <Card className="space-y-3 p-5">
      <div>
        <h3 className="text-lg">{t("Tabung perkataan Indonesia", "Indonesian word list")}</h3>
        <p className="mt-1 text-[12px] text-muted">{t("Perkataan atau frasa Indonesia yang masih terlepas. Setiap penulis AI (draf, slaid, FAQ) diberitahu untuk mengelaknya, dan semakan menyekat kelulusan jika ia muncul dalam kapsyen atau slaid. FAQ yang mengandunginya ditanda perlu semakan.",
          "Indonesian words or phrases that still slip through. Every AI writer (drafts, slides, FAQ) is told to avoid them, and the check blocks approval if one appears in a caption or slide. An FAQ that contains one is marked needs check.")}</p>
      </div>
      <form onSubmit={add} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
        <Input value={indo} onChange={(e) => setIndo(e.target.value)} placeholder={t("Perkataan Indonesia (cth: memakai)", "Indonesian word (e.g. memakai)")} aria-label={t("Perkataan Indonesia", "Indonesian word")} />
        <Input value={bm} onChange={(e) => setBm(e.target.value)} placeholder={t("Guna ini (cth: menggunakan), pilihan", "Use this instead (e.g. menggunakan), optional")} aria-label={t("Perkataan Malaysia", "Malaysian word")} />
        <Button type="submit" size="sm" disabled={busy || !indo.trim()}><Plus size={12} /> {t("Tambah", "Add")}</Button>
      </form>
      {rows.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {rows.map((r, i) => (
            <li key={r.indo} className="inline-flex items-center gap-1.5 rounded-pill border border-line bg-surface-2/60 px-3 py-1 text-xs">
              <s className="text-danger">{r.indo}</s>{r.bm && <span>→ <b>{r.bm}</b></span>}
              <button type="button" aria-label={t("Buang {w}", "Remove {w}", { w: r.indo })} disabled={busy} className="text-muted hover:text-danger"
                onClick={() => persist(rows.filter((_, j) => j !== i), t('"{w}" dibuang daripada tabung.', '"{w}" removed from the list.', { w: r.indo }))}><Trash2 size={11} /></button>
            </li>
          ))}
        </ul>
      ) : <p className="text-[12px] text-muted">{t("Tabung masih kosong.", "The list is still empty.")}</p>}
      <p className="text-[11px] text-muted">{t("Sudah disekat tanpa perlu ditambah: {list}.", "Already blocked without being added: {list}.", { list: BUILT_IN_INDO.join(", ") })}</p>
    </Card>
  );
}

/* One run of Mireld (Wan, 26 Sep 2026: "can we try mireld for 1 run to scan and do the image"). The next scrape and the
   next worker run that has something to ask each ask Mireld FIRST: summaries, drafts, and the read of a picture.
   rootsys answers whatever Mireld cannot, so nothing is lost. Each part then reports here and switches itself off
   (backend/semasa/trial.py). The row is made by the worker, which the browser cannot do. */
function MireldTrial({ settings, save, onToast }) {
  const { t } = useLang();
  const [busy, setBusy] = useState(false);
  const row = settings.llm_trial;
  const v = row || {};
  const waiting = v.scrape === true || v.media === true;

  async function start() {
    setBusy(true);
    try {
      await save("llm_trial", { ...v, scrape: true, media: true, requested_at: new Date().toISOString() });
      onToast(t("Percubaan dimulakan: scrape seterusnya dan kerja bot seterusnya akan tanya Mireld dahulu.",
        "Trial set: the next scrape and the bot's next job will ask Mireld first."), "ok");
    } catch (e) {
      onToast(/not found/.test(e.message)
        ? t("Suis ini dibuat oleh bot pada larian pertamanya selepas kemas kini ini (dalam 15 minit). Cuba lagi selepas itu.",
          "The bot makes this switch on its first run after this update (within 15 minutes). Try again after that.")
        : e.message, "danger");
    }
    setBusy(false);
  }

  const Result = ({ label, r }) => (!r ? null : (
    <div className="min-w-0 rounded-tile bg-surface-2/60 p-3 text-[12px]">
      <p className="font-semibold">{label} · <span className={r.ok ? "text-ok" : "text-danger"}>{r.ok ? t("Mireld menjawab", "Mireld answered") : t("Mireld tidak menjawab", "Mireld did not answer")}</span>
        <span className="font-normal text-muted"> · {stampMYT(r.at)}</span></p>
      {r.why ? <p className="mt-1 [overflow-wrap:anywhere] text-muted">{r.why}</p> : (
        <ul className="mt-1 space-y-0.5 text-muted">
          <li>{t("Model", "Model")}: <b className="text-ink">{r.model}</b></li>
          <li>{t("Jawapan Mireld {a}, gagal {m} · rootsys menjawab {r}", "Mireld answered {a}, missed {m} · rootsys answered {r}",
            { a: r.mireld_answers, m: r.mireld_misses, r: r.rootsys_answers })}</li>
          <li>{t("Gambar dibaca oleh Mireld {a}, tidak dapat dibaca {b} · oleh rootsys {c}", "Pictures read by Mireld {a}, not read {b} · by rootsys {c}",
            { a: r.picture_read_by_mireld, b: r.picture_not_read_by_mireld, c: r.picture_read_by_rootsys })}</li>
          <li className="[overflow-wrap:anywhere]">{t("Model dalam senarai Mireld", "Models Mireld lists")}: {r.models?.length || 0}
            {r.image_models?.length ? ` · ${t("nampak seperti model gambar", "look like image models")}: ${r.image_models.join(", ")}` : ""}</li>
          {r.stopped && <li className="text-warn">{r.stopped}</li>}
          {r.run && <li><a className="text-accent underline" href={r.run} target="_blank" rel="noopener noreferrer">{t("Buka larian", "Open the run")}</a></li>}
        </ul>
      )}
    </div>
  ));

  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-lg"><FlaskConical size={17} /> {t("Cuba Mireld untuk satu larian", "Try Mireld for one run")}</h3>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            {t("Scrape seterusnya dan kerja bot seterusnya bertanya Mireld dahulu: ringkasan berita, draf, dan bacaan gambar. rootsys menjawab apa yang Mireld tidak dapat, jadi tiada kerja hilang. Keputusan muncul di sini dan percubaan berhenti sendiri.",
              "The next scrape and the bot's next job ask Mireld first: the news summaries, the drafts, and the read of a picture. rootsys answers what Mireld cannot, so no work is lost. The result appears here and the trial switches itself off.")}</p>
        </div>
        <Button onClick={start} disabled={busy || waiting || !row}>{waiting ? t("Menunggu larian…", "Waiting for a run…") : t("Cuba sekali", "Try once")}</Button>
      </div>
      {!row && <p className="text-[12px] text-muted">{t("Suis ini muncul selepas bot berjalan sekali dengan kemas kini ini.", "This switch appears after the bot has run once with this update.")}</p>}
      {waiting && <p className="text-[12px] text-muted">{t("Menunggu: {p}. Scrape berjalan tiga kali sehari (untuk cepat: GitHub → Actions → Scrape isu semasa → Run workflow); bahagian bot berjalan pada kerja seterusnya yang bertanya penulis.",
        "Waiting for: {p}. A scrape runs three times a day (to hurry it: GitHub → Actions → Scrape isu semasa → Run workflow); the bot's part runs on its next job that asks the writer.",
        { p: [v.scrape === true && "scrape", v.media === true && t("kerja bot", "bot job")].filter(Boolean).join(", ") })}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        <Result label="Scrape" r={v.scrape_result} />
        <Result label={t("Kerja bot", "Bot job")} r={v.media_result} />
      </div>
    </Card>
  );
}

/* The three AI slots, set here instead of only in GitHub (Wan, 27 Sep 2026: "can add in setting reader, image
   generation, image reader key and endpoint"). supabase/016_ai_settings.sql keeps each key where the page can never
   read it back, and bound to the endpoint it was typed with; the worker lays these over the GitHub secrets
   (backend/semasa/ai_config.py). An empty field keeps what GitHub says. */
const AI_SLOTS = [
  { slot: "reader", icon: ScrollText, providers: ["openai", "anthropic"],
    bm: "Pembaca & penulis teks", en: "Text reader & writer",
    whatBm: "membaca berita, menulis idea, draf, FAQ", whatEn: "reads the news, writes ideas, drafts, FAQ" },
  { slot: "image_gen", icon: ImagePlus, providers: ["cloudflare", "openai", "replicate"],
    bm: "Penjana gambar", en: "Image generation",
    whatBm: "melukis latar, suntingan AI botol", whatEn: "draws backgrounds and the AI bottle edit" },
  { slot: "image_reader", icon: Eye, providers: ["openai", "anthropic"],
    bm: "Pembaca gambar", en: "Image reader",
    whatBm: "membaca rujukan, menyemak label botol", whatEn: "reads references, checks the bottle label" },
];
const PROVIDER_LABEL = { openai: "OpenAI-compatible", anthropic: "Anthropic", cloudflare: "Cloudflare Workers AI", replicate: "Replicate" };
const ENDPOINT_HINT = {
  openai: "https://…/v1", anthropic: "https://api.anthropic.com", cloudflare: "Account ID (32)", replicate: "",
};
/* What GitHub's secrets and variables say, as the worker last loaded them (backend/semasa/ai_config.py record_github).
   A GitHub secret can never be read back, so a key shows only as set, with its last 4 characters, like the page's own. */
const hostPath = (u) => (u || "").replace(/^https:\/\//, "");
function githubOf(github, slot) {
  const runs = [github?.media, github?.scrape].filter((x) => x && typeof x === "object" && x[slot]);
  if (slot !== "image_gen") runs.sort((a, b) => String(b.at || "").localeCompare(String(a.at || "")));
  const run = runs[0];
  return run ? { ...run[slot], at: run.at, from: run === github?.media ? "media" : "scrape" } : null;
}
function githubFacts(slot, g, t) {
  const key = (k) => (k ? `${t("kunci", "key")} ${k}` : t("tiada kunci", "no key"));
  if (slot === "image_gen") {
    const p = g.provider, c = g[p] || {};
    if (p === "cloudflare") return [PROVIDER_LABEL[p], `${t("akaun", "account")} ${c.account || t("tiada", "none")}`, c.model, `${t("suntingan", "edit")} ${c.edit_model}`, `token ${c.key || t("tiada", "none")}`];
    if (p === "openai") return [PROVIDER_LABEL[p], hostPath(c.base_url), c.model, key(c.key)];
    return [PROVIDER_LABEL[p] || p, c.model, `${t("suntingan", "edit")} ${c.edit_model}`, `token ${c.key || t("tiada", "none")}`];
  }
  const facts = [PROVIDER_LABEL[g.provider] || g.provider, hostPath(g.base_url), g.model, key(g.key)];
  return slot === "image_reader" ? [t("alamat penulis", "the writer's endpoint"), ...facts.slice(1)] : facts;
}
function GithubNow({ slot, github, overridden }) {
  const { t } = useLang();
  const g = githubOf(github, slot);
  if (!g) {
    return <p className="text-[11px] text-muted" data-github-now="none">{t(
      "GitHub: belum dilaporkan. Dipaparkan selepas larian seterusnya (media setiap 15 minit, scrape tiga kali sehari).",
      "GitHub: not reported yet. Shown after the next run (media every 15 minutes, scrape three times a day).")}</p>;
  }
  const fb = slot === "reader" && g.fallback?.base_url ? g.fallback : null;
  return (
    <div className="rounded-tile border border-line bg-surface px-2.5 py-1.5 text-[11px] text-muted" data-github-now={slot}>
      <p className="break-words"><span className="font-medium text-ink">{t("Dalam GitHub", "In GitHub")}:</span>{" "}
        {githubFacts(slot, g, t).filter(Boolean).join(" · ")}</p>
      {fb && <p className="break-words">{t("Sandaran", "Backup")}: {hostPath(fb.base_url)} · {fb.model || "—"} · {fb.key ? `${t("kunci", "key")} ${fb.key}` : t("tiada kunci", "no key")}</p>}
      {g.blocked && <p className="text-danger">{g.blocked}</p>}
      {fb?.blocked && <p className="text-danger">{fb.blocked}</p>}
      <p>{t("Dibaca oleh larian {w}, {at}.", "Read by the {w} run, {at}.", { w: g.from, at: stampMYT(g.at) })}{" "}
        {overridden ? t("Medan yang anda isi di bawah mengatasi ini; medan kosong masih guna GitHub.", "The fields you filled below win over this; empty fields still use GitHub.")
                    : t("Inilah yang digunakan sekarang.", "This is what is in use now.")}</p>
    </div>
  );
}

const blankAi = (slot) => ({ provider: slot === "image_gen" ? "cloudflare" : "openai", base_url: "", model: "", edit_model: "", key: "" });

function AiSettings({ onToast, github }) {
  const { t } = useLang();
  const [rows, setRows] = useState({});
  const [forms, setForms] = useState({});
  const [busy, setBusy] = useState("");
  const [missing, setMissing] = useState(false);

  // `only`: after saving one slot, refresh that slot's form alone, so what is typed in the others (a key included)
  // is not wiped by the reload
  async function load(only) {
    const { data, error } = await supabase.from(TABLES.aiConfig).select("*");
    if (error) { setMissing(true); return; }
    setMissing(false);
    const by = Object.fromEntries((data || []).map((r) => [r.slot, r]));
    setRows(by);
    const formOf = (slot) => {
      const r = by[slot];
      return r ? { provider: r.provider, base_url: r.base_url || "", model: r.model || "", edit_model: r.edit_model || "", key: "" } : blankAi(slot);
    };
    setForms((f) => Object.fromEntries(AI_SLOTS.map(({ slot }) => [slot, !only || only === slot || !f[slot] ? formOf(slot) : f[slot]])));
  }
  useEffect(() => { load(); }, []);

  const set = (slot, k, v) => setForms((f) => ({ ...f, [slot]: { ...f[slot], [k]: v } }));

  async function saveSlot(slot, clearKey = false) {
    const f = forms[slot];
    setBusy(slot);
    const { data, error } = await supabase.rpc("semasa_save_ai_slot", {
      p_slot: slot, p_provider: f.provider, p_base_url: f.base_url, p_model: f.model, p_edit_model: f.edit_model,
      p_key: clearKey ? null : (f.key || null), p_clear_key: clearKey,
    });
    setBusy("");
    if (error) return onToast(errText(error), "danger");
    onToast(data?.key_dropped
      ? t("Disimpan. Kunci lama dibuang kerana alamat berubah: masukkan kunci untuk alamat baharu.", "Saved. The old key was dropped because the endpoint changed: enter the key for the new endpoint.")
      : t("Tetapan AI disimpan. Larian seterusnya menggunakannya.", "AI settings saved. The next run uses them."), data?.key_dropped ? "warn" : "ok");
    load(slot);
  }

  async function reset(slot) {
    setBusy(slot);
    const { error } = await supabase.rpc("semasa_clear_ai_slot", { p_slot: slot });
    setBusy("");
    if (error) return onToast(errText(error), "danger");
    onToast(t("Kembali kepada tetapan GitHub.", "Back to the GitHub settings."), "ok");
    load(slot);
  }

  if (missing) {
    return (
      <Card className="p-5 text-sm text-muted">
        <h3 className="flex items-center gap-2 text-lg text-ink"><KeyRound size={16} /> {t("Tetapan AI", "AI settings")}</h3>
        <p className="mt-1">{t("Jalankan supabase/016_ai_settings.sql dahulu.", "Run supabase/016_ai_settings.sql first.")}</p>
      </Card>
    );
  }

  return (
    <Card className="space-y-4 p-5">
      <div>
        <h3 className="flex items-center gap-2 text-lg"><KeyRound size={16} /> {t("Tetapan AI: kunci dan alamat", "AI settings: keys and endpoints")}</h3>
        <p className="mt-1 text-[12px] text-muted">{t(
          "Kosong = guna rahsia GitHub seperti sekarang. Kunci yang disimpan tidak akan dipaparkan semula (hanya 4 aksara terakhir), dan hanya dihantar ke alamat yang ditaip bersamanya. Tukar alamat tanpa kunci baharu, kunci lama dibuang.",
          "Empty = use the GitHub secrets as now. A saved key is never shown again (only its last 4 characters), and is only sent to the endpoint it was typed with. Change the endpoint without a new key and the old key is dropped.")}</p>
      </div>
      {AI_SLOTS.map(({ slot, icon: Icon, providers, bm, en, whatBm, whatEn }) => {
        const f = forms[slot] || blankAi(slot);
        const r = rows[slot];
        const cf = f.provider === "cloudflare", rep = f.provider === "replicate";
        return (
          <div key={slot} className="space-y-2 rounded-tile bg-surface-2/60 p-3" data-ai-slot={slot}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-2 text-sm font-medium"><Icon size={14} className="text-accent" /> {t(bm, en)}
                <span className="font-normal text-muted">· {t(whatBm, whatEn)}</span></p>
              <span className={`rounded-pill px-2 py-0.5 text-[11px] ${r ? "bg-accent/15 text-accent" : "bg-surface text-muted"}`}>
                {r ? t("dari laman ini", "from this page") : "GitHub"}{r?.key_hint ? ` · ${t("kunci", "key")} ${r.key_hint}` : ""}
              </span>
            </div>
            <GithubNow slot={slot} github={github} overridden={!!r} />
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block"><Label>{t("Penyedia", "Provider")}</Label>
                <Select className="w-full" value={f.provider} onChange={(v) => set(slot, "provider", v)}
                  options={providers.map((p) => [p, PROVIDER_LABEL[p]])} aria-label={t("Penyedia", "Provider")} /></label>
              {!rep && (
                <label className="block"><Label hint={ENDPOINT_HINT[f.provider]}>{cf ? "Cloudflare Account ID" : t("Alamat (endpoint)", "Endpoint")}</Label>
                  <Input value={f.base_url} onChange={(e) => set(slot, "base_url", e.target.value)} placeholder={ENDPOINT_HINT[f.provider]}
                    autoComplete="off" spellCheck={false} /></label>
              )}
              <label className="block"><Label hint={slot === "image_gen" ? t("gambar dari kata-kata", "picture from words") : ""}>{t("Model", "Model")}</Label>
                <Input value={f.model} onChange={(e) => set(slot, "model", e.target.value)} autoComplete="off" spellCheck={false}
                  placeholder={cf ? "@cf/black-forest-labs/flux-1-schnell" : rep ? "black-forest-labs/flux-1.1-pro" : f.provider === "anthropic" ? "claude-haiku-4-5-20251001" : "gpt-4o-mini"} /></label>
              {slot === "image_gen" && f.provider !== "openai" && (
                <label className="block"><Label hint={t("lukis semula DENGAN gambar botol", "redraws WITH the bottle photo")}>{t("Model suntingan", "Edit model")}</Label>
                  <Input value={f.edit_model} onChange={(e) => set(slot, "edit_model", e.target.value)} autoComplete="off" spellCheck={false}
                    placeholder={cf ? "@cf/black-forest-labs/flux-2-klein-4b" : "black-forest-labs/flux-kontext-pro"} /></label>
              )}
              <label className="block sm:col-span-2"><Label hint={r?.key_hint ? t("kosongkan untuk kekalkan {h}", "leave empty to keep {h}", { h: r.key_hint }) : t("disimpan tersembunyi", "stored hidden")}>{cf ? "API token" : t("Kunci API", "API key")}</Label>
                <Input type="password" value={f.key} onChange={(e) => set(slot, "key", e.target.value)} autoComplete="new-password" spellCheck={false} /></label>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => saveSlot(slot)} disabled={busy === slot}><Save size={12} /> {t("Simpan", "Save")}</Button>
              {r?.key_hint && <Button size="sm" variant="soft" onClick={() => saveSlot(slot, true)} disabled={busy === slot}>{t("Buang kunci", "Remove key")}</Button>}
              {r && <Button size="sm" variant="ghost" onClick={() => reset(slot)} disabled={busy === slot}><Trash2 size={12} /> {t("Guna GitHub semula", "Use GitHub again")}</Button>}
            </div>
          </div>
        );
      })}
    </Card>
  );
}

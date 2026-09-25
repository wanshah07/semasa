import { useEffect, useState } from "react";
import { Lock, Plus, Save, Trash2 } from "lucide-react";
import { dayNames } from "../lib/brand";
import { faqCategories } from "../lib/faqExport";
import { TABLES, supabase } from "../lib/SupabaseClient";
import { BUILT_IN_INDO } from "../lib/compliance";
import { useLang } from "../lib/i18n";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label } from "../components/ui/Field";

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

      <IndoTabung settings={settings} save={save} onToast={onToast} />

      <FaqCategories settings={settings} save={save} onToast={onToast} />
    </main>
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
    try { await save("bahasa", { ...(settings.bahasa || {}), indo: next }); setRows(next); onToast(msg, "ok"); } catch (e) {
      onToast(/0 rows/.test(e.message) ? t("Jalankan supabase/007_faq.sql dahulu (ia menyediakan tabung ini).", "Run supabase/007_faq.sql first (it sets up this list).") : e.message, "danger");
    }
    setBusy(false);
  }
  function add(e) {
    e.preventDefault();
    const w = indo.replace(/\s+/g, " ").trim().toLowerCase();
    if (!w) return;
    if (BUILT_IN_INDO.includes(w)) return onToast(t('"{w}" sudah dalam senarai terbina.', '"{w}" is already in the built-in list.', { w }), "info");
    if (rows.some((r) => r.indo.toLowerCase() === w)) return onToast(t('"{w}" sudah ada dalam tabung.', '"{w}" is already in the list.', { w }), "info");
    persist([...rows, { indo: w, bm: bm.trim() }], t('"{w}" ditambah. Semua penulis AI akan mengelaknya.', '"{w}" added. Every AI writer will avoid it.', { w }));
    setIndo(""); setBm("");
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

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Clock, Download, Droplets, ImagePlus, Loader2, Pencil, Plus, RotateCcw, Save, Search,
  Trash2, Wand2, X } from "lucide-react";
import { fadeUp } from "../design/motion";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { refusal, removeReference, uploadReference } from "../lib/storage";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label, Segmented, TextArea } from "../components/ui/Field";

/* Wangian (Wan, 26 Sep 2026: "add one more segment for fragrance, design is separate or can try to redesign via canva"
   and "you will run to find new design and will replace the bottle in the design with our by render or via canva").
   The page keeps the list of our perfumes and registers each step; the worker (backend/semasa/fragrance.py) writes three
   concepts, draws the one Wan picks TWO ways (our real bottle cut out and set into a new scene, and an AI edit with the
   bottle as its reference), and keeps the version he saves. Every word on the artwork is typeset, never drawn by the
   AI, and the badges carry only the claims listed on the perfume. Canva is done in a chat session, not here. */

const BLANK = { brand: "Valorith", name: "", concentration: "Extrait de Parfum", size: "", notes: "", mood: "", claims: "",
  footnote: "" };
const LAYOUT = { hero: ["Nama besar", "Big name"], behind: ["Tajuk di belakang botol", "Headline behind the bottle"],
  notes: ["Nota wangian", "Scent notes"] };
const METHOD = { cutout: ["Botol sebenar (dipotong)", "Real bottle (cut out)"], ai_edit: ["Suntingan AI", "AI edit"] };

export default function FragranceTab({ user, gens, onToast }) {
  const { t } = useLang();
  const [list, setList] = useState([]);
  const [error, setError] = useState("");
  const [sel, setSel] = useState("");
  const [editing, setEditing] = useState(null);             // null | "new" | a perfume row

  async function load() {
    const { data, error: e } = await supabase.from(TABLES.fragrances).select("*").order("created_at");
    if (e) setError(/semasa_fragrances/.test(errText(e))
      ? t("Wangian belum disediakan: jalankan supabase/014_fragrance.sql sekali.", "Fragrance is not set up yet: run supabase/014_fragrance.sql once.")
      : errText(e));
    else { setError(""); setList(data || []); }
  }
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!sel && list.length) setSel(list[0].id); }, [list, sel]);
  const p = list.find((x) => x.id === sel);
  const jobs = gens.rows.filter((r) => r.mode === "fragrance" && r.meta?.fragrance_id === sel);

  async function removePerfume(row) {
    if (!window.confirm(t("Padam {name} daripada senarai? Reka bentuk yang disimpan kekal.", "Delete {name} from the list? Saved designs stay.", { name: row.name }))) return;
    const { error: e } = await supabase.from(TABLES.fragrances).delete().eq("id", row.id);
    if (e) return onToast(errText(e), "danger");
    await Promise.all([removeReference(row.bottle_path), removeReference(row.logo_path)]).catch(() => {});
    if (sel === row.id) setSel("");
    onToast(t("Dipadam.", "Deleted."), "info"); load();
  }

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Wangian · reka bentuk iklan", "Fragrance · ad designs")}</p>
        <h1 className="mt-2 text-4xl leading-tight">{t("Reka bentuk baharu, dengan botol kita.", "New designs, with our bottle in them.")}</h1>
        <p className="mt-3 max-w-2xl text-sm text-muted">
          {t("Pilih wangian, cari tiga konsep (dari nota wangian, atau dari iklan rujukan yang anda muat naik), pilih satu. "
            + "Ia dilukis dua cara: botol sebenar dipotong dan diletak dalam babak baharu, dan suntingan AI dengan botol sebagai "
            + "rujukan. Anda simpan yang terbaik. Semua perkataan ditaip, bukan dilukis AI, dan lencana hanya membawa dakwaan yang "
            + "anda senaraikan. Mahu cuba di Canva? Beritahu saya dalam chat.",
          "Choose a perfume, find three concepts (from its notes, or from a reference ad you upload), and pick one. It is drawn "
            + "two ways: the real bottle cut out and set into a new scene, and an AI edit with the bottle as its reference. You "
            + "keep the better one. Every word is typeset, never drawn by the AI, and the badges carry only the claims you list. "
            + "Want to try it in Canva? Tell me in the chat.")}
        </p>
      </motion.div>
      {error && <p className="mt-6 rounded-tile bg-danger/10 p-3 text-sm text-danger">{error}</p>}

      <div className="mt-8 grid items-start gap-5 lg:grid-cols-[300px_1fr]">
        <Card className="min-w-0 p-4">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-lg">{t("Wangian kita", "Our perfumes")}</h2>
            <Button size="sm" variant="soft" onClick={() => setEditing("new")}><Plus size={12} /> {t("Tambah", "Add")}</Button>
          </div>
          {list.length === 0 && !error && <p className="text-sm text-muted">{t("Belum ada. Tambah wangian pertama.", "None yet. Add the first perfume.")}</p>}
          <ul className="space-y-2">
            {list.map((row) => (
              <li key={row.id}>
                <button type="button" onClick={() => setSel(row.id)}
                  className={`flex w-full min-w-0 items-center gap-3 rounded-tile border p-2 text-left transition ${sel === row.id ? "border-accent bg-surface-2" : "border-line hover:bg-surface-2"}`}>
                  {row.bottle_url ? <img src={row.bottle_url} alt="" className="h-12 w-12 shrink-0 rounded object-contain bg-bg" />
                    : <span className="grid h-12 w-12 shrink-0 place-items-center rounded bg-surface-2 text-muted"><Droplets size={18} /></span>}
                  <span className="min-w-0">
                    <b className="block truncate text-sm">{row.brand} {row.name}</b>
                    <span className="block truncate text-[11px] text-muted">{[row.concentration, row.size].filter(Boolean).join(" · ")}</span>
                    {!row.bottle_url && <span className="block text-[11px] text-warn">{t("Tiada gambar botol", "No bottle photo")}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <div className="min-w-0 space-y-5">
          {p && (
            <Card className="min-w-0 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="text-xl [overflow-wrap:anywhere]">{p.brand} {p.name}</h2>
                  <p className="text-[12px] text-muted [overflow-wrap:anywhere]">{p.notes || t("Tiada nota wangian", "No scent notes")}</p>
                  <p className="mt-1 text-[12px] [overflow-wrap:anywhere]"><b>{t("Dakwaan diluluskan", "Approved claims")}:</b> {(p.claims || []).join(" · ") || t("tiada (tiada lencana dakwaan)", "none (no claim badges)")}</p>
                </div>
                <span className="flex gap-1">
                  <Button size="sm" variant="soft" onClick={() => setEditing(p)}><Pencil size={12} /> {t("Ubah", "Edit")}</Button>
                  <Button size="sm" variant="danger" title={t("Padam", "Delete")} onClick={() => removePerfume(p)}><Trash2 size={12} /></Button>
                </span>
              </div>
              <FindConcepts p={p} user={user} gens={gens} onToast={onToast} />
            </Card>
          )}
          {p && <Jobs rows={jobs} user={user} gens={gens} onToast={onToast} />}
        </div>
      </div>

      {editing && <PerfumeForm row={editing === "new" ? null : editing} user={user} onToast={onToast}
        onClose={() => setEditing(null)} onSaved={(id) => { setEditing(null); setSel(id); load(); }} />}
    </main>
  );
}

function PerfumeForm({ row, user, onToast, onClose, onSaved }) {
  const { t } = useLang();
  const [f, setF] = useState(() => (row ? { ...BLANK, ...row, claims: (row.claims || []).join("\n") } : { ...BLANK }));
  const [bottle, setBottle] = useState(null);
  const [logo, setLogo] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  function pick(setter, pngOnly) {
    return (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      const why = refusal(file) || (pngOnly && file.type !== "image/png" ? t("Logo mesti PNG lutsinar.", "The logo must be a transparent PNG.") : "");
      if (why) return onToast(why, "warn");
      setter(file);
    };
  }

  async function save(e) {
    e.preventDefault();
    if (!f.name.trim()) return onToast(t("Nama wangian diperlukan.", "The perfume needs a name."), "warn");
    setBusy(true);
    const made = [];
    try {
      const out = {
        brand: f.brand.trim() || "Valorith", name: f.name.trim(), concentration: f.concentration.trim(), size: f.size.trim(),
        notes: f.notes.trim(), mood: f.mood.trim(), footnote: f.footnote.trim(),
        claims: f.claims.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 8),
      };
      if (bottle) { const up = await uploadReference(user, bottle); made.push(up.path); out.bottle_url = up.url; out.bottle_path = up.path; }
      if (logo) { const up = await uploadReference(user, logo); made.push(up.path); out.logo_url = up.url; out.logo_path = up.path; }
      const q = row ? supabase.from(TABLES.fragrances).update(out).eq("id", row.id)
        : supabase.from(TABLES.fragrances).insert({ ...out, created_by: user.id });
      const { data, error } = await q.select("id").single();
      if (error) throw new Error(errText(error));
      // a replaced photo: the old file goes once the new one is saved
      if (row && bottle && row.bottle_path) await removeReference(row.bottle_path).catch(() => {});
      if (row && logo && row.logo_path) await removeReference(row.logo_path).catch(() => {});
      onToast(t("Disimpan.", "Saved."), "ok");
      onSaved(data.id);
    } catch (err) {
      await Promise.all(made.map((x) => removeReference(x))).catch(() => {});
      onToast(err.message || String(err), "danger");
    } finally { setBusy(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 pt-10" onClick={onClose}>
      <form onSubmit={save} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true"
        className="w-full max-w-xl space-y-3 rounded-card border border-line bg-surface p-5 shadow-lift">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-lg">{row ? t("Ubah wangian", "Edit perfume") : t("Tambah wangian", "Add a perfume")}</h3>
          <button type="button" onClick={onClose} className="text-muted hover:text-ink" aria-label={t("Tutup", "Close")}><X size={16} /></button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block"><Label>{t("Jenama", "Brand")}</Label><Input value={f.brand} onChange={set("brand")} maxLength={40} /></label>
          <label className="block"><Label>{t("Nama", "Name")}</Label><Input value={f.name} onChange={set("name")} maxLength={40} placeholder="Noir Rush" required /></label>
          <label className="block"><Label>{t("Kepekatan", "Concentration")}</Label><Input value={f.concentration} onChange={set("concentration")} maxLength={40} /></label>
          <label className="block"><Label>{t("Saiz", "Size")}</Label><Input value={f.size} onChange={set("size")} maxLength={20} placeholder="30ml" /></label>
        </div>
        <label className="block"><Label hint={t("konsep dilukis dari sini", "the concepts are drawn from these")}>{t("Nota wangian", "Scent notes")}</Label>
          <TextArea rows={3} value={f.notes} onChange={set("notes")} maxLength={600}
            placeholder={t("Atas: bergamot, lada merah jambu. Tengah: mawar, oud. Dasar: ambar, vanila, musk.", "Top: bergamot, pink pepper. Heart: rose, oud. Base: amber, vanilla, musk.")} /></label>
        <label className="block"><Label>{t("Suasana", "Mood")}</Label>
          <Input value={f.mood} onChange={set("mood")} maxLength={160} placeholder={t("gelap, hangat, mewah", "dark, warm, luxurious")} /></label>
        <label className="block"><Label hint={t("satu sebaris; hanya yang ada bukti dalam PIF", "one a line; only those with evidence in the PIF")}>{t("Dakwaan diluluskan (lencana)", "Approved claims (badges)")}</Label>
          <TextArea rows={3} value={f.claims} onChange={set("claims")} maxLength={400} placeholder={t("Tahan lebih 8 jam*", "More than 8 hours lasting*")} /></label>
        <label className="block"><Label hint={t("untuk dakwaan bertanda *", "for a claim marked *")}>{t("Nota kaki", "Footnote")}</Label>
          <Input value={f.footnote} onChange={set("footnote")} maxLength={120} placeholder={t("*Berdasarkan kepekatan minyak 25%", "*Based on 25% oil concentration")} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block cursor-pointer rounded-tile border border-dashed border-line p-3 text-[12px] hover:bg-surface-2">
            <span className="flex items-center gap-2 font-semibold"><ImagePlus size={14} /> {t("Gambar botol", "Bottle photo")}</span>
            <span className="mt-1 block text-muted">{bottle ? bottle.name : row?.bottle_url ? t("Ada. Pilih untuk tukar.", "Set. Choose to replace.") : t("PNG lutsinar, atau latar putih kosong", "A transparent PNG, or on a plain white background")}</span>
            <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={pick(setBottle, false)} />
          </label>
          <label className="block cursor-pointer rounded-tile border border-dashed border-line p-3 text-[12px] hover:bg-surface-2">
            <span className="flex items-center gap-2 font-semibold"><ImagePlus size={14} /> {t("Logo (pilihan)", "Logo (optional)")}</span>
            <span className="mt-1 block text-muted">{logo ? logo.name : row?.logo_url ? t("Ada. Pilih untuk tukar.", "Set. Choose to replace.") : t("PNG lutsinar; tanpa logo, nama jenama ditaip", "A transparent PNG; without one the brand name is typeset")}</span>
            <input type="file" accept="image/png" className="sr-only" onChange={pick(setLogo, true)} />
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>{t("Batal", "Cancel")}</Button>
          <Button type="submit" disabled={busy}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} {t("Simpan", "Save")}</Button>
        </div>
      </form>
    </div>
  );
}

function FindConcepts({ p, user, gens, onToast }) {
  const { t } = useLang();
  const [ref, setRef] = useState(null);
  const [format, setFormat] = useState("square");
  const [busy, setBusy] = useState(false);
  const preview = useMemo(() => (ref ? URL.createObjectURL(ref) : ""), [ref]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function go() {
    setBusy(true);
    let up = null;
    try {
      if (ref) up = await uploadReference(user, ref);
      const { error } = await supabase.from(TABLES.media).insert({
        mode: "fragrance", type: "image", status: "pending", created_by: user.id, provider: null,
        meta: { step: "concepts", fragrance_id: p.id, format, ...(up ? { style_ref: { url: up.url, path: up.path, name: ref.name } } : {}) },
      });
      if (error) throw new Error(/mode_check/.test(errText(error))
        ? t("Jalankan supabase/014_fragrance.sql sekali dahulu.", "Run supabase/014_fragrance.sql once first.") : errText(error));
      setRef(null);
      onToast(t("Dihantar. Tiga konsep dalam beberapa minit.", "Sent. Three concepts within a few minutes."), "ok");
      gens.reload();
    } catch (err) {
      if (up) await removeReference(up.path).catch(() => {});
      onToast(err.message || String(err), "danger");
    } finally { setBusy(false); }
  }

  return (
    <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-line pt-4">
      <label className="flex min-w-0 cursor-pointer items-center gap-2 rounded-tile border border-dashed border-line p-2 text-[12px] hover:bg-surface-2">
        {preview ? <img src={preview} alt="" className="h-10 w-10 shrink-0 rounded object-cover" /> : <ImagePlus size={16} className="shrink-0" />}
        <span className="min-w-0">
          <b className="block">{t("Iklan rujukan (pilihan)", "Reference ad (optional)")}</b>
          <span className="block truncate text-muted">{ref ? ref.name : t("Susun atur dan suasana diambil; karya dan jenamanya tidak", "Its layout and mood are taken; never its artwork or brand")}</span>
        </span>
        <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only"
          onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (!file) return; const why = refusal(file); if (why) onToast(why, "warn"); else setRef(file); }} />
      </label>
      {ref && <button type="button" onClick={() => setRef(null)} className="text-[11px] text-muted hover:text-ink">{t("Buang rujukan", "Remove reference")}</button>}
      <Segmented value={format} onChange={setFormat} options={[["square", "1:1"], ["portrait", "4:5"]]} />
      <Button onClick={go} disabled={busy || !p.bottle_url} title={p.bottle_url ? "" : t("Tambah gambar botol dahulu", "Add a bottle photo first")}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />} {t("Cari reka bentuk", "Find designs")}</Button>
      {!p.bottle_url && <p className="w-full text-[11px] text-warn">{t("Tambah gambar botol (Ubah) sebelum mencari reka bentuk.", "Add a bottle photo (Edit) before finding designs.")}</p>}
    </div>
  );
}

function Jobs({ rows, user, gens, onToast }) {
  const { t } = useLang();
  if (!rows.length) {
    return <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">
      {t("Belum ada reka bentuk untuk wangian ini.", "No designs for this perfume yet.")}</p>;
  }
  return <div className="space-y-4">{rows.map((r) => <Job key={r.id} r={r} mine={user && r.created_by === user.id} gens={gens} onToast={onToast} />)}</div>;
}

function Job({ r, mine, gens, onToast }) {
  const { t, lang } = useLang();
  const L = (pair) => (lang === "en" ? pair[1] : pair[0]);
  const m = r.meta || {};
  const step = m.step || "concepts";
  const [busy, setBusy] = useState(false);
  const [again, setAgain] = useState(false);
  const [checked, setChecked] = useState({});
  const working = r.status === "pending" || r.status === "processing";

  async function send(patch, msg) {
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.media)
      .update({ status: "pending", attempts: 0, error: null, meta: { ...m, ...patch } }).eq("id", r.id).select("id");
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    if (!data?.length) return onToast(t("Tidak disimpan: hanya orang yang membuatnya boleh mengubahnya.", "Not saved: only the person who made it can change it."), "warn");
    onToast(msg, "ok"); setAgain(false); gens.reload();
  }
  async function discard() {
    if (!window.confirm(t("Buang reka bentuk ini dan failnya?", "Discard this design and its files?"))) return;
    if (!(m.renders || []).length) {           // nothing drawn yet: the row goes now, and the reference with it
      try { await gens.remove(r); await removeReference(m.style_ref?.path).catch(() => {}); onToast(t("Dibuang.", "Discarded."), "info"); }
      catch (e) { onToast(e.message || String(e), "danger"); }
      return;
    }
    send({ step: "discard" }, t("Dibuang dalam beberapa minit.", "Discarded within a few minutes."));
  }

  const Icon = r.status === "error" ? AlertTriangle : working ? (r.status === "processing" ? Loader2 : Clock) : CheckCircle2;
  const label = r.status === "error" ? t("Gagal", "Failed")
    : working ? ({ concepts: t("Mencari konsep", "Finding concepts"), render: t("Melukis 2 versi", "Drawing 2 versions"),
      save: t("Menyimpan", "Saving"), discard: t("Membuang", "Discarding") }[step] || t("Menunggu", "Waiting"))
    : ({ choose: t("Pilih konsep", "Pick a concept"), pick: t("Pilih versi untuk disimpan", "Pick the version to keep"),
      saved: t("Disimpan", "Saved") }[step] || t("Siap", "Done"));
  const tone = r.status === "error" ? "bg-danger/10 text-danger" : step === "saved" && !working ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn";

  return (
    <Card className="min-w-0 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
        <span className={`inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 font-semibold ${tone}`}>
          <Icon size={12} className={r.status === "processing" ? "animate-spin" : ""} /> {label}</span>
        <span className="text-muted">{m.format === "portrait" ? "4:5 · 1080×1350" : "1:1 · 1080×1080"} · {timeAgo(r.created_at)}</span>
      </div>
      {m.style_ref?.url && (
        <div className="mt-3 flex min-w-0 gap-2 rounded-tile bg-surface-2/70 p-2 text-[12px]">
          <img src={m.style_ref.url} alt="" className="h-12 w-12 shrink-0 rounded object-cover" />
          <div className="min-w-0">
            <b>{t("Iklan rujukan", "Reference ad")}</b>
            {m.review?.unread ? <p className="text-warn [overflow-wrap:anywhere]">{t("Tidak dibaca", "Not read")}: {m.review.unread}</p>
              : m.review ? <p className="[overflow-wrap:anywhere]">{(m.review.keep || []).join(" · ") || m.review.mood}</p> : null}
          </div>
        </div>
      )}
      {r.error && <p className="mt-3 rounded-tile bg-danger/5 p-2 text-[12px] text-danger [overflow-wrap:anywhere]">{r.error}</p>}

      {(m.renders || []).length > 0 && (
        <div className={`mt-3 grid gap-3 ${m.renders.length > 1 ? "sm:grid-cols-2" : ""}`}>
          {m.renders.map((x) => (
            <figure key={x.path || x.url} className="min-w-0">
              <a href={x.url} target="_blank" rel="noopener noreferrer"><img src={x.url} alt="" loading="lazy" className="w-full rounded-tile bg-surface-2 object-contain" /></a>
              <figcaption className="mt-1.5 space-y-1 text-[12px]">
                <b className="block">{L(METHOD[x.method] || [x.method, x.method])}</b>
                {x.method === "cutout" && <p className="text-ok">{t("Botol dan label ialah gambar sebenar anda: tepat.", "The bottle and label are your real photo: exact.")}</p>}
                {x.method === "ai_edit" && (x.label ? (x.label.ok
                  ? <p className="text-ok">{t("Label dibaca: {reads}", "Label reads: {reads}", { reads: x.label.reads })}</p>
                  : <p className="text-danger [overflow-wrap:anywhere]">{t("Label SALAH: AI menulis \"{reads}\". Tiada: {missing}.", "Label WRONG: the AI wrote \"{reads}\". Missing: {missing}.", { reads: x.label.reads || "—", missing: (x.label.missing || []).join(", ") || "—" })}
                    {x.label.attempts > 1 ? ` ${t("(dilukis 2 kali)", "(drawn twice)")}` : ""}</p>)
                  : <p className="text-warn">{t("Label belum disemak oleh AI: semak sendiri.", "The label was not checked: check it yourself.")}</p>)}
                {mine && step === "pick" && !working && (() => {
                  // an AI redraw whose label was not read back correctly is not kept without Wan's own check
                  const guarded = x.method === "ai_edit" && !x.label?.ok;
                  return (
                    <>
                      {guarded && (
                        <label className="flex items-start gap-1.5 text-[11px]">
                          <input type="checkbox" className="mt-0.5" checked={!!checked[x.method]} onChange={(e) => setChecked({ ...checked, [x.method]: e.target.checked })} />
                          <span>{t("Saya sudah semak: nama, kepekatan dan saiz pada botol tepat.", "I have checked it: the name, concentration and size on the bottle are right.")}</span>
                        </label>
                      )}
                      <Button size="sm" disabled={busy || (guarded && !checked[x.method])} onClick={() => send({ step: "save", chosen: x.method }, t("Disimpan; yang satu lagi dibuang.", "Saved; the other one is discarded."))}>
                        <Save size={12} /> {t("Simpan yang ini", "Keep this one")}</Button>
                    </>
                  );
                })()}
                {step === "saved" && <a href={x.url} target="_blank" rel="noopener noreferrer" download className="inline-flex items-center gap-1 text-accent hover:underline"><Download size={12} /> {t("Muat turun", "Download")}</a>}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      {Object.entries(m.render_errors || {}).map(([k, v]) => (
        <p key={k} className="mt-2 text-[11px] text-warn [overflow-wrap:anywhere]">{L(METHOD[k] || [k, k])} {t("tidak dapat dilukis", "could not be drawn")}: {v}</p>
      ))}
      {step === "saved" && <p className="mt-2 text-[11px] text-muted">{t("Akan dijadualkan ke Valorith bila penerbitan Semasa dihidupkan. Buat masa ini, muat turun.", "It will be scheduled to Valorith once Semasa's publishing is switched on. For now, download it.")}</p>}

      {(m.concepts || []).length > 0 && (step === "choose" || (step === "pick" && again) || (r.status === "error" && step === "render")) && (
        <Concepts m={m} mine={mine} busy={busy || working} onRender={(patch) => send({ step: "render", ...patch }, t("Dihantar. Dua versi dalam beberapa minit.", "Sent. Two versions within a few minutes."))} />
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {mine && step === "pick" && !working && (m.concepts || []).length > 0 && (
          <Button size="sm" variant="soft" onClick={() => setAgain(!again)}><Wand2 size={12} /> {again ? t("Tutup konsep", "Hide concepts") : t("Cuba konsep lain", "Try another concept")}</Button>
        )}
        {mine && (
          <span className="ml-auto flex gap-1">
            {r.status === "error" && <Button size="sm" variant="soft" title={t("Cuba lagi", "Try again")}
              onClick={async () => { try { await gens.requeue(r.id); onToast(t("Dimasukkan semula ke giliran.", "Put back in the queue."), "ok"); } catch (e) { onToast(e.message, "danger"); } }}><RotateCcw size={12} /></Button>}
            {r.status !== "processing" && step !== "discard" && <Button size="sm" variant="danger" title={t("Buang", "Discard")} disabled={busy} onClick={discard}><Trash2 size={12} /></Button>}
          </span>
        )}
      </div>
    </Card>
  );
}

function Concepts({ m, mine, busy, onRender }) {
  const { t, lang } = useLang();
  const L = (pair) => (lang === "en" ? pair[1] : pair[0]);
  const [pick, setPick] = useState(m.pick ?? 0);
  const [head, setHead] = useState({});
  const [methods, setMethods] = useState({ cutout: true, ai_edit: true });
  const chosen = m.concepts[pick] || m.concepts[0];
  const words = head[pick] || { headline: chosen.headline, tagline: chosen.tagline };
  const setWords = (k) => (e) => setHead({ ...head, [pick]: { ...words, [k]: e.target.value } });
  const useMethods = Object.keys(methods).filter((k) => methods[k]);

  return (
    <div className="mt-3 space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        {m.concepts.map((c, i) => (
          <button type="button" key={i} onClick={() => setPick(i)} disabled={!mine}
            className={`min-w-0 rounded-tile border p-3 text-left text-[12px] transition ${pick === i ? "border-accent bg-surface-2" : "border-line hover:bg-surface-2"}`}>
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 shrink-0 rounded-full border border-line" style={{ background: c.ink }} />
              <span className="h-3 w-3 shrink-0 rounded-full border border-line" style={{ background: c.accent }} />
              <b className="truncate">{c.title}</b>
            </span>
            <span className="mt-1 block text-muted">{L(LAYOUT[c.layout] || [c.layout, c.layout])}</span>
            <span className="mt-1.5 block font-semibold [overflow-wrap:anywhere]">{c.headline}{c.tagline ? ` · ${c.tagline}` : ""}</span>
            {c.why && <span className="mt-1 block [overflow-wrap:anywhere]">{c.why}</span>}
            <span className="mt-1 block text-muted [overflow-wrap:anywhere]">{c.scene}</span>
            {c.badges?.length > 0 && <span className="mt-1 block [overflow-wrap:anywhere]">{t("Lencana", "Badges")}: {c.badges.join(" · ")}</span>}
            {c.callouts?.length > 0 && <span className="mt-1 block [overflow-wrap:anywhere]">{c.callouts.map((k) => k.title).join(" · ")}</span>}
          </button>
        ))}
      </div>
      {mine && (
        <div className="flex flex-wrap items-end gap-3 rounded-tile bg-surface-2/70 p-3">
          <label className="block w-full min-w-0 sm:w-auto sm:flex-1"><Label>{t("Tajuk", "Headline")}</Label>
            <Input value={words.headline} onChange={setWords("headline")} maxLength={40} /></label>
          {chosen.layout === "hero" && <label className="block w-full min-w-0 sm:w-auto sm:flex-1"><Label>{t("Slogan", "Tagline")}</Label>
            <Input value={words.tagline} onChange={setWords("tagline")} maxLength={40} /></label>}
          <span className="flex flex-wrap gap-3 text-[12px]">
            {Object.keys(METHOD).map((k) => (
              <label key={k} className="inline-flex items-center gap-1.5">
                <input type="checkbox" checked={methods[k]} onChange={(e) => setMethods({ ...methods, [k]: e.target.checked })} /> {L(METHOD[k])}
              </label>
            ))}
          </span>
          <Button size="sm" disabled={busy || !useMethods.length || !words.headline.trim()}
            onClick={() => onRender({ pick, methods: useMethods, edits: { headline: words.headline.trim().toUpperCase(), tagline: (words.tagline || "").trim().toUpperCase() } })}>
            <Wand2 size={12} /> {t("Lukis", "Draw")}</Button>
        </div>
      )}
    </div>
  );
}

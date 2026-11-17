import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Pencil, Plus, RotateCcw, Trash2, Wand2 } from "lucide-react";
import { STREAMS } from "../lib/brand";
import { BUILT_IN, LIMITS, blankScript, comicLibrary, comicMeta, comicStage, entryProblem, episodeLine, formScript, newId, nextEpisode,
  redrawMeta, scriptFlags, scriptProblem, withEntry, withoutEntry, wordsNote } from "../lib/comic";
import { flagWords } from "../lib/complianceBm";
import { useLang } from "../lib/i18n";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import ComicDailyPanel from "./ComicDailyPanel";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

/* Comic as a Design choice (Wan, 16 to 17 Nov 2026: "add comic as choice", "make it series like cartoon series", "remember the comic
   style so other model can use"). The page only registers a job, as for a poster: the worker (backend/semasa/comic_job.py) writes the
   script from the idea when asked, has a picture maker draw it in the chosen style with the series' own two people, reads the words
   back and compares them with the script, and frames it with the series and episode. Styles and series are rules/comic.json plus
   Wan's own (settings row `comic`). */

const count = (s) => [...String(s ?? "")].length;

function Flags({ flags }) {
  const { lang } = useLang();
  if (!flags.length) return null;
  return (
    <ul className="space-y-1 text-[12px]" data-comic-flags>
      {flags.map((f, i) => (
        <li key={i} className={`flex items-start gap-1.5 [overflow-wrap:anywhere] ${f.hard ? "text-danger" : "text-warn"}`}>
          <AlertTriangle size={12} className="mt-0.5 shrink-0" /> <span><b>{flagWords(f, lang).where}</b>: {flagWords(f, lang).msg}</span></li>
      ))}
    </ul>
  );
}

/* The script by hand: a title, then four panels of one or two bubbles. The cast is the series' own and is not typed here. */
export function ComicScriptEditor({ value, onChange, series, disabled = false }) {
  const { t } = useLang();
  const names = { A: series?.cast?.A?.name || "A", B: series?.cast?.B?.name || "B" };
  const setPanel = (i, patch) => onChange({ ...value, panels: value.panels.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const setLine = (i, k, patch) => {
    const lines = value.panels[i].lines.map((l, j) => (j === k ? { ...l, ...patch } : l));
    if (patch.who && lines.length === 2) lines[k === 0 ? 1 : 0] = { ...lines[k === 0 ? 1 : 0], who: patch.who === "A" ? "B" : "A" };
    setPanel(i, { lines });
  };
  const where = [t("kiri atas", "top left"), t("kanan atas", "top right"), t("kiri bawah", "bottom left"), t("kanan bawah", "bottom right")];
  return (
    <div className="space-y-3" data-comic-script>
      <label className="block"><Label hint={`${count(value.title)}/${LIMITS.title}`}>{t("Tajuk di atas komik", "Title above the comic")}</Label>
        <Input value={value.title} disabled={disabled} onChange={(e) => onChange({ ...value, title: e.target.value })} maxLength={LIMITS.title + 40}
          placeholder={t("Cth: Logo halal bukan hijau. Palsu ke?", "E.g. The halal logo is not green. Is it fake?")} /></label>
      <label className="block"><Label hint={t("pilihan · kosong = tempat biasa siri ini", "optional · empty = the series' usual place")}>{t("Tempat episod ini", "This episode's place")}</Label>
        <Input value={value.setting} disabled={disabled} onChange={(e) => onChange({ ...value, setting: e.target.value })} maxLength={LIMITS.setting}
          placeholder={series?.setting || ""} /></label>
      <div className="grid gap-3 md:grid-cols-2">
        {value.panels.map((p, i) => (
          <div key={i} className="rounded-tile bg-surface-2/60 p-3">
            <p className="mb-1.5 text-[13px] font-semibold text-accent">{t("Panel {n}", "Panel {n}", { n: i + 1 })} <span className="font-normal text-muted">· {where[i]}</span></p>
            <TextArea rows={2} value={p.scene} disabled={disabled} onChange={(e) => setPanel(i, { scene: e.target.value })} maxLength={LIMITS.scene}
              aria-label={t("Babak panel {n}", "Panel {n} scene", { n: i + 1 })}
              placeholder={t("Babak untuk pelukis: apa yang dua watak ini buat dan rasa. Tiada teks, papan tanda atau logo.", "The scene for the artist: what the two are doing and feeling. No text, signs or logos.")} />
            {p.lines.map((l, k) => (
              <div key={k} className="mt-2 flex items-start gap-2">
                <Select value={l.who} disabled={disabled} onChange={(who) => setLine(i, k, { who })} className="shrink-0"
                  aria-label={t("Siapa bercakap", "Who speaks")} options={[["A", names.A], ["B", names.B]]} />
                <div className="min-w-0 flex-1">
                  <TextArea rows={2} value={l.text} disabled={disabled} onChange={(e) => setLine(i, k, { text: e.target.value })}
                    aria-label={t("Gelembung {k} panel {n}", "Bubble {k} of panel {n}", { k: k + 1, n: i + 1 })}
                    placeholder={k === 0 ? t("Apa yang dikatakan", "What is said") : t("Gelembung kedua (pilihan)", "A second bubble (optional)")} />
                  <span className={`text-[10.5px] ${count(l.text.trim()) > LIMITS.chars ? "text-danger" : "text-muted"}`}>{count(l.text.trim())}/{LIMITS.chars}</span>
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

const blankStyle = () => ({ id: "", name: "", about: "", prompt: "", lettering: "" });
const blankSeries = () => ({ id: "", name: "", about: "", setting: "", cast: { A: { name: "", look: "", role: "", voice: "" }, B: { name: "", look: "", role: "", voice: "" } } });
const one = (v) => (v && typeof v === "object" ? v.bm || v.en || "" : v || "");

/* Wan's own styles and series. A built-in one can be edited (his copy replaces it) and put back; his own can be deleted. */
function ComicLibraryEditor({ value, lib, canSave, saveSetting, onToast }) {
  const { t, lang } = useLang();
  const [kind, setKind] = useState("styles");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const items = lib[kind];
  const say = (x) => (lang === "en" ? x.en : x.bm);

  async function save(next, msg) {
    if (!next) return onToast(t("Belum lengkap.", "Not complete yet."), "warn");
    setBusy(true);
    try {
      await saveSetting("comic", next);
      onToast(msg, "ok");
      setDraft(null);
    } catch (e) {
      onToast(/not found/.test(e.message || "") ? t("Belum disediakan: jalankan supabase/085_comic.sql sekali dalam Supabase, kemudian cuba lagi.",
        "Not set up yet: run supabase/085_comic.sql once in Supabase, then try again.") : (e.message || String(e)), "danger");
    } finally {
      setBusy(false);
    }
  }
  function submit() {
    const taken = lib[kind].map((x) => x.id);
    const entry = { ...draft, id: draft.id || newId(kind === "styles" ? one(draft.name) : draft.name, taken) };
    const why = entryProblem(kind, entry);
    if (why) return onToast(why, "warn");
    return save(withEntry(value, kind, entry), t("Disimpan. Komik seterusnya menggunakannya.", "Saved. The next comic uses it."));
  }
  const edit = (x) => setDraft(kind === "styles"
    ? { id: x.id, name: one(x.name), about: one(x.about), prompt: x.prompt, lettering: x.lettering || "" }
    : { id: x.id, name: x.name, about: one(x.about), setting: x.setting || "", cast: { A: { ...x.cast.A }, B: { ...x.cast.B } } });
  const setCast = (who, patch) => setDraft({ ...draft, cast: { ...draft.cast, [who]: { ...draft.cast[who], ...patch } } });

  return (
    <details className="mt-6 rounded-card border border-line/80 bg-surface p-4" data-comic-library>
      <summary className="cursor-pointer text-sm font-semibold">{t("Gaya dan siri komik saya", "My comic styles and series")}
        <span className="ml-2 font-normal text-muted">{t("{a} gaya · {b} siri", "{a} styles · {b} series", { a: lib.styles.length, b: lib.series.length })}</span></summary>
      <p className="mt-2 max-w-3xl text-[12px] text-muted">{t("Gaya ialah penerangan bertulis yang dihantar kepada pelukis gambar, perkataan demi perkataan, setiap kali. Itulah cara gaya diingati dan cara pelukis lain melukis rupa yang sama. Rupa setiap watak siri juga diulang tepat pada setiap episod.",
        "A style is a written description sent to the picture maker word for word, every time. That is how a style is remembered and how another picture maker draws the same look. Each character's appearance is also repeated exactly in every episode.")}</p>
      {!canSave && <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px] text-warn">{t("Untuk simpan gaya dan siri sendiri, jalankan supabase/085_comic.sql sekali dalam Supabase. Gaya dan siri terbina sudah boleh digunakan.",
        "To save your own styles and series, run supabase/085_comic.sql once in Supabase. The built-in styles and series can be used already.")}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Segmented value={kind} onChange={(k) => { setKind(k); setDraft(null); }} options={[["styles", t("Gaya", "Styles")], ["series", t("Siri", "Series")]]} />
        <Button type="button" size="sm" variant="soft" onClick={() => setDraft(kind === "styles" ? blankStyle() : blankSeries())}>
          <Plus size={12} /> {kind === "styles" ? t("Gaya baharu", "New style") : t("Siri baharu", "New series")}</Button>
      </div>
      <ul className="mt-3 grid gap-2 md:grid-cols-2">
        {items.map((x) => (
          <li key={x.id} className="rounded-tile border border-line p-2.5 text-[12px]">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 font-semibold [overflow-wrap:anywhere]">{kind === "styles" ? say(x.name) : x.name}
                {x.own && <span className="ml-1.5 rounded-pill bg-accent/10 px-1.5 py-0.5 text-[10px] font-normal text-accent">{t("saya", "mine")}</span>}
                {x.edited && <span className="ml-1.5 rounded-pill bg-warn/10 px-1.5 py-0.5 text-[10px] font-normal text-warn">{t("diubah", "edited")}</span>}</p>
              <span className="flex shrink-0 gap-1">
                <button type="button" onClick={() => edit(x)} className="rounded p-1 text-muted hover:text-accent" aria-label={t("Ubah", "Edit")}><Pencil size={13} /></button>
                {(x.own || x.edited) && <button type="button" disabled={busy} aria-label={x.own ? t("Padam", "Delete") : t("Kembali kepada asal", "Back to the original")}
                  title={x.own ? t("Padam", "Delete") : t("Kembali kepada asal", "Back to the original")}
                  onClick={() => { if (window.confirm(x.own ? t("Padam yang ini? Komik lama tidak berubah.", "Delete this one? Earlier comics do not change.") : t("Kembalikan kepada yang asal?", "Put the original back?"))) save(withoutEntry(value, kind, x.id), x.own ? t("Dipadam.", "Deleted.") : t("Dikembalikan kepada asal.", "Back to the original.")); }}
                  className="rounded p-1 text-muted hover:text-danger">{x.own ? <Trash2 size={13} /> : <RotateCcw size={13} />}</button>}
              </span>
            </div>
            <p className="mt-0.5 text-muted [overflow-wrap:anywhere]">{say(x.about)}</p>
            {kind === "series" && <p className="mt-1 [overflow-wrap:anywhere]"><b>{x.cast.A.name}</b> {t("dan", "and")} <b>{x.cast.B.name}</b></p>}
          </li>
        ))}
      </ul>
      {draft && kind === "styles" && (
        <div className="mt-3 space-y-2 rounded-tile bg-surface-2/60 p-3" data-comic-style-form>
          <div className="grid gap-2 md:grid-cols-2">
            <label className="block"><Label>{t("Nama gaya", "Style name")}</Label><Input value={draft.name} maxLength={LIMITS.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label className="block"><Label hint={t("satu baris untuk halaman ini", "one line for this page")}>{t("Ringkasan", "Summary")}</Label><Input value={draft.about} maxLength={LIMITS.about} onChange={(e) => setDraft({ ...draft, about: e.target.value })} /></label>
          </div>
          <label className="block"><Label hint={`${count(draft.prompt)}/${LIMITS.style_prompt} · ${t("dalam bahasa Inggeris, untuk pelukis gambar", "in English, for the picture maker")}`}>{t("Penerangan gaya", "Style description")}</Label>
            <TextArea rows={6} value={draft.prompt} onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
              placeholder="LINE: ... COLOUR: ... SHADING: ... PROPORTIONS: ... FACES: ... BACKGROUND: ... FINISH: ..." /></label>
          <label className="block"><Label hint={`${count(draft.lettering)}/${LIMITS.lettering} · ${t("gelembung dan huruf, apabila pelukis menulis perkataan", "bubbles and letters, when the picture maker writes the words")}`}>{t("Huruf", "Lettering")}</Label>
            <TextArea rows={2} value={draft.lettering} onChange={(e) => setDraft({ ...draft, lettering: e.target.value })} /></label>
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(null)}>{t("Batal", "Cancel")}</Button>
            <Button type="button" size="sm" disabled={busy} onClick={submit}>{busy && <Loader2 size={12} className="animate-spin" />} {t("Simpan gaya", "Save style")}</Button>
          </div>
        </div>
      )}
      {draft && kind === "series" && (
        <div className="mt-3 space-y-2 rounded-tile bg-surface-2/60 p-3" data-comic-series-form>
          <div className="grid gap-2 md:grid-cols-2">
            <label className="block"><Label hint={t("dicetak pada poster", "printed on the poster")}>{t("Nama siri", "Series name")}</Label><Input value={draft.name} maxLength={LIMITS.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
            <label className="block"><Label>{t("Ringkasan", "Summary")}</Label><Input value={draft.about} maxLength={LIMITS.about} onChange={(e) => setDraft({ ...draft, about: e.target.value })} /></label>
          </div>
          <label className="block"><Label hint={t("dalam bahasa Inggeris, untuk pelukis gambar", "in English, for the picture maker")}>{t("Tempat biasa", "Usual place")}</Label>
            <TextArea rows={2} value={draft.setting} maxLength={LIMITS.setting} onChange={(e) => setDraft({ ...draft, setting: e.target.value })} /></label>
          <div className="grid gap-3 md:grid-cols-2">
            {["A", "B"].map((who) => (
              <div key={who} className="space-y-2 rounded-tile border border-line p-2.5">
                <p className="text-[12px] font-semibold text-accent">{who === "A" ? t("Watak A · sentiasa di kiri", "Character A · always on the left") : t("Watak B · sentiasa di kanan", "Character B · always on the right")}</p>
                <Input value={draft.cast[who].name} maxLength={LIMITS.name} placeholder={t("Nama", "Name")} aria-label={t("Nama watak {w}", "Character {w} name", { w: who })} onChange={(e) => setCast(who, { name: e.target.value })} />
                <TextArea rows={3} value={draft.cast[who].look} aria-label={t("Rupa watak {w}", "Character {w} appearance", { w: who })} onChange={(e) => setCast(who, { look: e.target.value })}
                  placeholder={t("Rupa yang tepat, dalam bahasa Inggeris: umur, wajah, rambut atau tudung, pakaian, warna. Diulang tepat setiap episod.", "The exact appearance, in English: age, face, hair or tudung, clothes, colours. Repeated exactly every episode.")} />
                <span className="block text-[10.5px] text-muted">{count(draft.cast[who].look)}/{LIMITS.look}</span>
                <Input value={draft.cast[who].role} maxLength={LIMITS.role} placeholder={t("Peranan (untuk penulis skrip)", "Role (for the script writer)")} aria-label={t("Peranan watak {w}", "Character {w} role", { w: who })} onChange={(e) => setCast(who, { role: e.target.value })} />
                <Input value={draft.cast[who].voice} maxLength={LIMITS.voice} placeholder={t("Cara bercakap (untuk penulis skrip)", "Manner of speaking (for the script writer)")} aria-label={t("Cara bercakap watak {w}", "Character {w} manner of speaking", { w: who })} onChange={(e) => setCast(who, { voice: e.target.value })} />
              </div>
            ))}
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(null)}>{t("Batal", "Cancel")}</Button>
            <Button type="button" size="sm" disabled={busy} onClick={submit}>{busy && <Loader2 size={12} className="animate-spin" />} {t("Simpan siri", "Save series")}</Button>
          </div>
        </div>
      )}
    </details>
  );
}

/* The comic form: series, style, stream, the idea or the script, and how the words get onto the picture. */
export default function ComicMaker({ user, gens, posts, brand, settings, saveSetting, onToast, kindPicker, go }) {
  const { t, lang } = useLang();
  const value = settings?.comic;
  const lib = useMemo(() => comicLibrary(value), [value]);
  const [stream, setStream] = useState("regulab");
  const [seriesId, setSeriesId] = useState("");
  const [styleId, setStyleId] = useState("");
  const [by, setBy] = useState("ai");                       // ai | own
  const [brief, setBrief] = useState("");
  const [review, setReview] = useState(true);
  const [script, setScript] = useState(blankScript);
  const [source, setSource] = useState("");
  const [wordsMode, setWordsMode] = useState("auto");
  const [attach, setAttach] = useState("");
  const [episode, setEpisode] = useState("");
  const [busy, setBusy] = useState(false);
  const series = lib.series.find((s) => s.id === seriesId) || lib.series.find((s) => s.id === lib.defaultSeries) || lib.series[0];
  const style = lib.styles.find((s) => s.id === styleId) || lib.styles.find((s) => s.id === lib.defaultStyle) || lib.styles[0];
  const say = (x) => (lang === "en" ? x.en : x.bm);
  const drafts = (posts?.rows || []).filter((p) => p.status === "draft");
  const next = nextEpisode(gens.rows, series.id);
  const problem = by === "own" ? scriptProblem(script, source) : "";
  const flags = useMemo(() => (by === "own" ? scriptFlags(script, stream, source, brand?.regulab) : []), [by, script, stream, source, brand]);
  const ready = by === "ai" ? brief.trim().length > 0 : !problem && !flags.some((f) => f.hard);

  async function submit(e) {
    e.preventDefault();
    if (!ready) return onToast(problem || t("Lengkapkan idea atau skrip dahulu.", "Fill in the idea or the script first."), "warn");
    setBusy(true);
    try {
      const meta = comicMeta({ stream, series, style, source, brief, script: by === "own" ? script : null, review, wordsMode, episode });
      const ins = await supabase.from(TABLES.media).insert({ mode: "slides", type: "image", status: "pending", created_by: user.id, prompt: "", post_id: attach || null, meta });
      if (ins.error) throw new Error(errText(ins.error));
      onToast(by === "ai" && review
        ? t("Dalam giliran. Semasa tulis skrip dahulu; baca dan tekan Lukis di Pustaka poster.", "Queued. Semasa writes the script first; read it and press Draw in the Poster library.")
        : t("Dalam giliran. Komik muncul di Pustaka poster dalam beberapa minit.", "Queued. The comic appears in the Poster library within a few minutes."), "ok");
      gens.reload();
    } catch (err) {
      onToast(err.message || String(err), "danger");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card as="form" onSubmit={submit} className="mt-2 p-5 sm:p-6" data-comic-form>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="min-w-0 space-y-4">
            {kindPicker}
            <div><Label>{t("Untuk", "For")}</Label><Segmented value={stream} onChange={setStream} options={STREAMS} />
              <span className="mt-1 block text-[11px] text-muted">{stream === "linkedin"
                ? t("Bahasa Inggeris untuk rakan seprofesion. Tiada logo, laman web atau nama syarikat pada komik.", "English for peers. No logo, website or company name on the comic.")
                : t("Bahasa Malaysia santai untuk pemilik PKS. Logo dan laman web ws.regulab pada bingkai.", "Casual Malaysian Malay for SME owners. The ws.regulab logo and website on the frame.")}</span></div>
            <label className="block"><Label hint={t("dua watak yang sama pada setiap episod", "the same two people in every episode")}>{t("Siri", "Series")}</Label>
              <Select value={series.id} onChange={setSeriesId} className="w-full" aria-label={t("Siri", "Series")} data-comic-series
                options={lib.series.map((s) => [s.id, s.name])} />
              <span className="mt-1 block text-[11px] text-muted [overflow-wrap:anywhere]">{say(series.about)}</span>
              <span className="mt-1 block text-[11px] [overflow-wrap:anywhere]"><b>{series.cast.A.name}</b> ({t("kiri", "left")}) · <b>{series.cast.B.name}</b> ({t("kanan", "right")})</span>
            </label>
            <label className="block"><Label hint={t("pilihan · kosong = episod seterusnya siri ini", "optional · empty = the series' next episode")}>{t("Nombor episod", "Episode number")}</Label>
              <Input value={episode} inputMode="numeric" className="max-w-[9rem]" onChange={(e) => setEpisode(e.target.value.replace(/\D/g, "").slice(0, 4))} placeholder={String(next)} />
              <span className="mt-1 block text-[12px]" data-comic-episode>{t("Poster akan tertulis", "The poster will read")}: <b>{episodeLine(series.name, Number(episode) > 0 ? Number(episode) : next, stream === "linkedin" ? "en" : "bm")}</b></span>
            </label>
            <label className="block"><Label hint={t("instrumen atau pengawal selia; dicetak di bawah komik", "the instrument or regulator; printed under the comic")}>{t("Sumber", "Source")}</Label>
              <Input value={source} onChange={(e) => setSource(e.target.value)} maxLength={LIMITS.source} placeholder="MPPHM (Domestik) 2020, Klausa 40(2)" /></label>
            <label className="block"><Label hint={t("pilihan · ditambah pada gambar post draf itu", "optional · added to that draft post's pictures")}>{t("Lampirkan pada post", "Attach to a post")}</Label>
              <Select value={attach} onChange={setAttach} className="w-full" aria-label={t("Lampirkan pada post", "Attach to a post")}
                options={[["", t("Tidak", "No")], ...drafts.slice(0, 150).map((p) => [p.id, `${p.date || t("Tiada", "None")} · ${(p.hook || "").slice(0, 60) || p.id.slice(0, 8)}`])]} /></label>
          </div>
          <div className="min-w-0 space-y-4">
            <div><Label hint={t("dihantar kepada pelukis perkataan demi perkataan", "sent to the picture maker word for word")}>{t("Gaya kartun", "Cartoon style")}</Label>
              <div role="radiogroup" aria-label={t("Gaya kartun", "Cartoon style")} className="grid gap-2 sm:grid-cols-2" data-comic-styles>
                {lib.styles.map((s) => (
                  <button key={s.id} type="button" role="radio" aria-checked={style.id === s.id} onClick={() => setStyleId(s.id)}
                    className={`rounded-tile border p-2.5 text-left ${style.id === s.id ? "border-accent ring-2 ring-accent/30" : "border-line hover:border-accent/60"}`}>
                    <span className="block text-[13px] font-semibold [overflow-wrap:anywhere]">{say(s.name)}
                      {!BUILT_IN.styles.includes(s.id) && <span className="ml-1.5 rounded-pill bg-accent/10 px-1.5 py-0.5 text-[10px] font-normal text-accent">{t("saya", "mine")}</span>}</span>
                    <span className="mt-0.5 block text-[11px] text-muted [overflow-wrap:anywhere]">{say(s.about)}</span>
                  </button>
                ))}
              </div>
            </div>
            <div><Label>{t("Perkataan dalam gelembung", "Words in the bubbles")}</Label>
              <Segmented value={wordsMode} onChange={setWordsMode} options={[["auto", t("Pelukis tulis, Semasa semak", "The picture maker writes, Semasa checks")], ["art", t("Semasa cetak sendiri", "Semasa prints them")]]} />
              <span className="mt-1 block text-[11px] text-muted">{wordsMode === "auto"
                ? t("Nampak lebih asli. Gambar dibaca semula dan setiap gelembung dibanding dengan skrip; jika berbeza ia dilukis sekali lagi, dan jika masih berbeza Semasa cetak perkataan sendiri.",
                  "Looks more natural. The picture is read back and every bubble is compared with the script; a difference is drawn once more, and if it still differs Semasa prints the words itself.")
                : t("Pelukis lukis watak tanpa perkataan; Semasa cetak gelembung, tepat seperti skrip.", "The picture maker draws the people with no words; Semasa prints the bubbles, exactly as the script has them.")}</span></div>
          </div>
        </div>

        <div className="mt-5 border-t border-line pt-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label>{t("Skrip", "Script")}</Label>
            <Segmented value={by} onChange={setBy} options={[["ai", t("Semasa tulis daripada idea", "Semasa writes from an idea")], ["own", t("Saya tulis sendiri", "I write it")]]} />
          </div>
          {by === "ai" ? (
            <div className="mt-2 space-y-2">
              <label className="block"><Label hint={t("empat panel, satu atau dua gelembung setiap panel; hanya fakta dalam idea ini digunakan", "four panels, one or two bubbles each; only the facts in this idea are used")}>{t("Idea atau prompt", "Idea or prompt")}</Label>
                <TextArea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={4000} data-comic-brief
                  placeholder={t("Cth: logo halal tidak semestinya hijau; MPPHM (Domestik) 2020 Klausa 40(2) benarkan warna ikut pembungkusan selagi spesifikasi tidak diubah",
                    "E.g. a halal logo need not be green; MPPHM (Domestik) 2020 Klausa 40(2) allows a colour that suits the pack as long as the specification is unchanged")} /></label>
              <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={review} onChange={(e) => setReview(e.target.checked)} />
                {t("Tunjuk skrip dahulu; lukis hanya selepas saya baca", "Show me the script first; draw only after I read it")}</label>
            </div>
          ) : (
            <div className="mt-2"><ComicScriptEditor value={script} onChange={setScript} series={series} /></div>
          )}
          {by === "own" && problem && <p className="mt-3 text-[12px] text-warn" data-comic-problem>{problem}</p>}
          <div className="mt-3"><Flags flags={flags} /></div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
          <span className="text-xs text-muted">1080 × 1350 · {t("watak dilukis oleh pelukis gambar AI", "the people are drawn by an AI picture maker")}</span>
          <Button type="submit" disabled={busy || !ready}>{busy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />} {t("Jana komik", "Make the comic")}</Button>
        </div>
      </Card>
      <ComicDailyPanel settings={settings} saveSetting={saveSetting} onToast={onToast} go={go} />
      <ComicLibraryEditor value={value} lib={lib} canSave={value !== undefined} saveSetting={saveSetting} onToast={onToast} />
      {go && <p className="mt-6 text-sm text-muted">{t("Hasil ada di", "Results are in")}{" "}
        <button type="button" className="text-accent underline" onClick={() => go("design-lib")}>{t("Pustaka poster", "the Poster library")}</button></p>}
    </>
  );
}

/* On a comic's card in the library: its series and episode, how the words got there, and the script. A script the writer wrote
   waits here for Wan (read, edit, Draw); a finished comic can be redrawn from an edited script, keeping its episode number. */
export function ComicCard({ row, mine, settings, brand, gens, onToast }) {
  const { t, lang } = useLang();
  const m = row.meta || {};
  const c = m.comic || {};
  const stage = comicStage(row);
  const lib = useMemo(() => comicLibrary(settings?.comic), [settings?.comic]);
  const series = lib.series.find((s) => s.id === c.series) || c.series_copy || lib.series[0];
  const [open, setOpen] = useState(stage === "script");
  const [script, setScript] = useState(() => formScript(c.script));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setScript(formScript(c.script)); }, [JSON.stringify(c.script)]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (stage === "script") setOpen(true); }, [stage]);
  const note = wordsNote(c.words);
  const problem = open ? scriptProblem(script, m.citation || "") : "";
  const flags = useMemo(() => (open ? scriptFlags(script, m.stream || "regulab", m.citation || "", brand?.regulab) : []), [open, script, m.stream, m.citation, brand]);
  const style = c.style_name ? { name: c.style_name } : lib.styles.find((x) => x.id === c.style) || c.style_copy;
  const styleName = style?.name ? (lang === "en" ? style.name.en : style.name.bm) : "";

  async function draw() {
    if (problem) return onToast(problem, "warn");
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.media)
      .update({ status: "pending", attempts: 0, error: null, meta: redrawMeta(m, script) }).eq("id", row.id).select("id");
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    if (!data?.length) return onToast(t("Tidak disimpan: hanya orang yang membuatnya boleh mengubahnya.", "Not saved: only the person who made it can change it."), "warn");
    onToast(t("Dihantar. Komik dilukis dalam beberapa minit.", "Sent. The comic is drawn within a few minutes."), "ok");
    setOpen(false);
    gens.reload();
  }

  return (
    <div className="mt-3 rounded-tile bg-surface-2/70 p-3 text-[12px]" data-comic-card>
      <p className="font-semibold [overflow-wrap:anywhere]">{c.episode_line || episodeLine(c.series_name || series?.name || "", c.episode || 0, m.stream === "linkedin" ? "en" : "bm")}
        {styleName && <span className="ml-2 rounded-pill bg-surface px-2 py-0.5 text-[10px] font-normal text-muted">{t("gaya", "style")}: {styleName}</span>}</p>
      {stage === "script" && <p className="mt-1.5 text-warn">{t("Skrip sudah ditulis dan menunggu anda. Baca, ubah jika perlu, kemudian tekan Lukis komik. Belum ada gambar dibuat.",
        "The script is written and waits for you. Read it, change it if needed, then press Draw the comic. No picture has been made yet.")}</p>}
      {note && <p className={`mt-1.5 [overflow-wrap:anywhere] ${note.tone === "ok" ? "text-ok" : "text-warn"}`} data-comic-words>{lang === "en" ? note.en : note.bm}</p>}
      {c.words?.other_text?.length > 0 && <p className="mt-1 text-warn [overflow-wrap:anywhere]">{t("Teks lain yang dibaca dalam gambar", "Other text read in the picture")}: {c.words.other_text.join(" · ")}</p>}
      {c.maker && <p className="mt-1 text-muted [overflow-wrap:anywhere]">{t("Dilukis oleh", "Drawn by")} {c.maker}{c.model ? ` · ${c.model}` : ""}{c.words?.draws ? ` · ${t("{n} lukisan", ["{n} drawing", "{n} drawings"], { n: c.words.draws })}` : ""}</p>}
      {mine && c.script && stage !== "working" && !open && (
        <Button size="sm" variant="soft" className="mt-2" onClick={() => setOpen(true)}><Pencil size={12} /> {t("Ubah skrip & lukis semula", "Edit the script & redraw")}</Button>
      )}
      {open && c.script && (
        <div className="mt-2.5 space-y-2">
          <ComicScriptEditor value={script} onChange={setScript} series={series} disabled={!mine || busy} />
          {problem && <p className="text-warn">{problem}</p>}
          <Flags flags={flags} />
          {mine && (
            <div className="flex flex-wrap justify-end gap-2">
              {stage !== "script" && <Button size="sm" variant="ghost" onClick={() => { setOpen(false); setScript(formScript(c.script)); }}>{t("Batal", "Cancel")}</Button>}
              <Button size="sm" disabled={busy || !!problem || flags.some((f) => f.hard)} onClick={draw} data-comic-draw>
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />} {stage === "script" ? t("Lukis komik", "Draw the comic") : t("Lukis semula", "Redraw")}</Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

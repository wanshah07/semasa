import { useMemo, useState } from "react";
import { Eye, EyeOff, Film, Loader2, Plus, Trash2 } from "lucide-react";
import { LIMITS, VOICES, castFromText, categoryProblem, howToFilm, newId, shortFilmLibrary, withCategory, withHidden,
  withoutCategory } from "../lib/shortFilms";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import { Input, Label, Select, TextArea } from "./ui/Field";

/* Short-film categories (Wan, 22 Nov 2026: "Untuk short film ada kan dua kategori - kisah keluarga halal dan cats, dan kategori ini
   boleh ditambah"). The two built-in ones are rules/short_films.json; Wan's own are the settings row `short_films`, written here
   (supabase/090_short_films.sql makes the row). The page only keeps the list: a film is made by hand in GitHub Actions with the
   category's id, and for one of his own the writer writes the scenes from its cast, place and style plus the day's topic. */

const blank = () => ({ name: "", about: "", cast: "", setting: "", style: "Photorealistic video.", scenes: "4", voice: VOICES[0], notes: "" });
const count = (s) => [...String(s ?? "")].length;

export default function ShortFilmCategories({ settings, saveSetting, onToast }) {
  const { t, lang } = useLang();
  const value = settings?.short_films;
  const canSave = value !== undefined && typeof saveSetting === "function";
  const lib = useMemo(() => shortFilmLibrary(value), [value]);
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [sure, setSure] = useState("");
  const say = (x) => (lang === "en" ? x.en : x.bm);
  const hiddenCount = lib.categories.filter((c) => c.hidden).length;
  const shown = lib.categories.filter((c) => showHidden || !c.hidden);

  async function save(next, msg, key) {
    if (!next) return onToast(t("Belum lengkap.", "Not complete yet."), "warn");
    setBusy(key);
    try {
      await saveSetting("short_films", next);
      onToast(msg, "ok");
      return true;
    } catch (e) {
      onToast(/not found/.test(e.message || "") ? t("Belum disediakan: jalankan supabase/090_short_films.sql sekali dalam Supabase, kemudian cuba lagi.",
        "Not set up yet: run supabase/090_short_films.sql once in Supabase, then try again.") : (e.message || String(e)), "danger");
      return false;
    } finally {
      setBusy("");
    }
  }

  function entryOf(d) {
    const taken = lib.categories.map((c) => c.id);
    return { id: newId(d.name, taken), name: d.name.trim(), about: d.about.trim(), cast: castFromText(d.cast), setting: d.setting.trim(),
      style: d.style.trim(), scene_count: Number(d.scenes), voice: { mode: "narrator", name: d.voice, notes: d.notes.trim() } };
  }
  async function add(e) {
    e.preventDefault();
    const entry = entryOf(draft);
    const why = categoryProblem(entry);
    if (why) return onToast(why, "warn");
    if (await save(withCategory(value, entry), t("Disimpan. Kategori ini boleh dijadikan filem.", "Saved. This category can be made into a film."), "add")) setDraft(null);
  }
  async function remove(c) {
    if (sure !== c.id) { setSure(c.id); return; }
    setSure("");
    await save(withoutCategory(value, c.id), t("Kategori dipadam.", "Category deleted."), c.id);
  }
  const hide = (c) => save(withHidden(value, c.id, !c.hidden),
    c.hidden ? t("Ditunjukkan semula.", "Shown again.") : t("Disembunyikan dari senarai. Ia masih boleh difilemkan dengan tangan.", "Hidden from the list. It can still be filmed by hand."), c.id);
  const set = (patch) => setDraft({ ...draft, ...patch });

  return (
    <details className="mt-6 rounded-card border border-line/80 bg-surface p-4" data-short-films>
      <summary className="cursor-pointer text-sm font-semibold">{t("Kategori filem pendek", "Short film categories")}
        <span className="ml-2 font-normal text-muted">{t("{n} kategori", "{n} categories", { n: lib.categories.length })}</span></summary>
      <p className="mt-2 max-w-3xl text-[12px] text-muted">{t(
        "Setiap kategori ialah satu jenis filem pendek: wataknya (rupa setiap watak diulang tepat dalam setiap babak), tempatnya dan gaya gambarnya. Filem dibuat dengan tangan di GitHub Actions dengan id kategori. Untuk kategori anda sendiri, Semasa menulis babak dan narasi daripada watak, tempat dan gaya itu serta topik hari itu.",
        "Each category is one kind of short film: its characters (each character's look is repeated exactly in every scene), its place and its picture style. A film is made by hand in GitHub Actions with the category's id. For a category of your own, Semasa writes the scenes and narration from those characters, place and style plus the day's topic.")}</p>
      {!canSave && <p className="mt-2 rounded-tile bg-warn/10 p-2 text-[12px] text-warn">{t("Untuk simpan kategori sendiri, jalankan supabase/090_short_films.sql sekali dalam Supabase. Dua kategori terbina sudah boleh difilemkan.",
        "To save your own categories, run supabase/090_short_films.sql once in Supabase. The two built-in categories can be filmed already.")}</p>}

      <ul className="mt-3 space-y-2">
        {shown.map((c) => {
          const how = howToFilm(c);
          return (
            <li key={c.id} className={`rounded-tile bg-surface-2/60 p-3 ${c.hidden ? "opacity-60" : ""}`} data-short-film={c.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold">{say(c.name)}
                    <span className="ml-2 text-[11px] font-normal text-muted">{c.builtIn ? t("terbina", "built-in") : t("anda", "yours")}
                      {c.hidden ? ` · ${t("disembunyikan", "hidden")}` : ""}</span></p>
                  {say(c.about) && <p className="mt-0.5 text-[12px] text-muted">{say(c.about)}</p>}
                  <p className="mt-1 text-[12px]">{c.cast.map((p) => p.name).join(", ")} · {t("{n} babak", "{n} scenes", { n: c.scene_count })} · {c.voice.mode === "narrator"
                    ? t("narator ({v})", "narrator ({v})", { v: c.voice.name }) : t("dialog dalam video", "dialogue inside the video")}
                    {c.builtIn ? "" : ` · ${t("babak ditulis oleh Semasa", "scenes written by Semasa")}`}</p>
                  <p className="mt-1 text-[11px] text-muted [overflow-wrap:anywhere]"><Film size={11} className="mr-1 inline" />{how.workflow} · {how.inputs}</p>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  {canSave && <Button type="button" size="sm" variant="ghost" disabled={!!busy} onClick={() => hide(c)}
                    aria-label={c.hidden ? t("Tunjuk", "Show") : t("Sembunyi", "Hide")}>
                    {busy === c.id ? <Loader2 size={12} className="animate-spin" /> : c.hidden ? <Eye size={12} /> : <EyeOff size={12} />}
                    {c.hidden ? t("Tunjuk", "Show") : t("Sembunyi", "Hide")}</Button>}
                  {canSave && c.own && <Button type="button" size="sm" variant={sure === c.id ? "danger" : "ghost"} disabled={!!busy} onClick={() => remove(c)}>
                    <Trash2 size={12} /> {sure === c.id ? t("Tekan lagi untuk padam", "Press again to delete") : t("Padam", "Delete")}</Button>}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      {hiddenCount > 0 && <button type="button" className="mt-2 text-[12px] text-accent underline" onClick={() => setShowHidden(!showHidden)}>
        {showHidden ? t("Sorok yang disembunyikan", "Leave out the hidden ones") : t("Tunjuk {n} yang disembunyikan", "Show {n} hidden", { n: hiddenCount })}</button>}

      {canSave && !draft && <div className="mt-3"><Button type="button" size="sm" variant="soft" onClick={() => setDraft(blank())}>
        <Plus size={12} /> {t("Tambah kategori", "Add category")}</Button></div>}
      {canSave && draft && (
        <form onSubmit={add} className="mt-3 space-y-3 rounded-tile border border-line/80 p-3" data-short-film-form>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block"><Label hint={`${count(draft.name)}/${LIMITS.name}`}>{t("Nama", "Name")}</Label>
              <Input value={draft.name} onChange={(e) => set({ name: e.target.value })} maxLength={LIMITS.name} placeholder={t("Cth: Arnab di kebun", "E.g. Rabbits in the garden")} /></label>
            <label className="block"><Label hint={t("pilihan", "optional")}>{t("Tentang", "About")}</Label>
              <Input value={draft.about} onChange={(e) => set({ about: e.target.value })} maxLength={LIMITS.about} placeholder={t("Satu ayat: kisah apa", "One sentence: what kind of story")} /></label>
          </div>
          <label className="block"><Label hint={t("satu baris setiap watak, paling banyak {n}", "one line per character, at most {n}", { n: LIMITS.cast })}>{t("Watak (Nama: rupa)", "Characters (Name: look)")}</Label>
            <TextArea rows={3} value={draft.cast} onChange={(e) => set({ cast: e.target.value })}
              placeholder={t("Tompok: arnab putih gebu dengan tompok coklat di telinga kiri dan mata hitam\nLabu: arnab kelabu kecil dengan ekor putih",
                "Tompok: a fluffy white rabbit with a brown patch on the left ear and black eyes\nLabu: a small grey rabbit with a white tail")} /></label>
          <label className="block"><Label hint={`${count(draft.setting)}/${LIMITS.setting}`}>{t("Tempat", "Place")}</Label>
            <Input value={draft.setting} onChange={(e) => set({ setting: e.target.value })} maxLength={LIMITS.setting} placeholder={t("Cth: kebun sayur di belakang rumah kampung", "E.g. a vegetable garden behind a kampung house")} /></label>
          <label className="block"><Label hint={t("dihantar kepada pembuat video dalam setiap babak", "sent to the video maker in every scene")}>{t("Gaya gambar", "Picture style")}</Label>
            <Input value={draft.style} onChange={(e) => set({ style: e.target.value })} maxLength={LIMITS.style} /></label>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="block"><Label>{t("Babak", "Scenes")}</Label>
              <Select value={draft.scenes} onChange={(scenes) => set({ scenes })} className="w-full"
                options={Array.from({ length: LIMITS.scenes_max - LIMITS.scenes_min + 1 }, (_, i) => [String(LIMITS.scenes_min + i), String(LIMITS.scenes_min + i)])} /></label>
            <label className="block"><Label>{t("Suara narator", "Narrator voice")}</Label>
              <Select value={draft.voice} onChange={(voice) => set({ voice })} className="w-full" options={VOICES.map((v) => [v, v])} /></label>
            <label className="block"><Label hint={t("pilihan", "optional")}>{t("Nada narasi", "Narration tone")}</Label>
              <Input value={draft.notes} onChange={(e) => set({ notes: e.target.value })} maxLength={LIMITS.voice_notes} placeholder={t("Cth: lembut, untuk kanak-kanak", "E.g. gentle, for children")} /></label>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(null)}>{t("Batal", "Cancel")}</Button>
            <Button type="submit" size="sm" disabled={busy === "add"}>{busy === "add" ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} {t("Simpan kategori", "Save category")}</Button>
          </div>
        </form>
      )}
    </details>
  );
}

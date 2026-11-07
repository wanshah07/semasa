import { useEffect, useRef, useState } from "react";
import { Save, Upload } from "lucide-react";
import { useLang } from "../lib/i18n";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { TextArea } from "./ui/Field";

/* Wan's own skill/prompt for motion videos (Wan, 23 Oct 2026: "add this skill/prompt to create motion"): added to every motion
   brief the worker writes from (backend/semasa/motion.py, settings.motion.prompt). It lived in Tetapan; Wan asked for the motion
   skills in one place with somewhere to upload them (11 Oct 2026), so it is on the Motion skills page now, and a .md or .txt
   skill file can be uploaded into it. An upload fills the box and is NOT saved until Save is pressed, so a wrong file costs nothing. */
export const SKILL_MAX = 6000;
const FILE_MAX = 200_000;                       // bytes: a skill file is text; anything bigger is not one

export default function MotionSkill({ settings, save, onToast }) {
  const { t } = useLang();
  const saved = settings.motion?.prompt || "";
  const [text, setText] = useState(saved);
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  useEffect(() => { setText(saved); }, [saved]);

  const submit = async () => {
    setBusy(true);
    try {
      await save("motion", { ...(settings.motion || {}), prompt: text.trim() });
      onToast(t("Disimpan: setiap video motion seterusnya mengikutnya.", "Saved: every motion video from now on follows it."), "ok");
    } catch (e) { onToast(/0 rows|motion/i.test(e.message) ? t("Jalankan supabase/043_motion.sql dahulu.", "Run supabase/043_motion.sql first.") : e.message, "danger"); }
    setBusy(false);
  };
  const take = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!/\.(md|markdown|txt)$/i.test(f.name) && !/^text\//.test(f.type)) return onToast(t("Muat naik fail .md atau .txt sahaja.", "Upload a .md or .txt file only."), "warn");
    if (f.size > FILE_MAX) return onToast(t("Fail terlalu besar untuk satu kemahiran (had 200 KB).", "That file is too big for a skill (200 KB limit)."), "warn");
    const body = (await f.text()).replace(/\r\n/g, "\n").trim();
    if (!body) return onToast(t("Fail itu kosong.", "That file is empty."), "warn");
    const next = text.trim() ? `${text.trim()}\n\n${body}` : body;
    setText(next.slice(0, SKILL_MAX));
    onToast(next.length > SKILL_MAX
      ? t("Dimasukkan, tetapi dipotong pada {n} aksara. Semak sebelum Simpan.", "Added, but cut at {n} characters. Check it before Save.", { n: SKILL_MAX })
      : t("Dimasukkan dari {f}. Tekan Simpan untuk menggunakannya.", "Added from {f}. Press Save to use it.", { f: f.name }), next.length > SKILL_MAX ? "warn" : "info");
  };
  return (
    <Card className="space-y-3 p-5" data-motion-prompt>
      <div>
        <h3 className="text-lg">{t("Kemahiran motion", "Motion skill")}</h3>
        <p className="mt-1 text-[12px] text-muted">{t("Arahan anda sendiri untuk video motion (gaya, rentak, warna, apa yang mesti ada). Kontrak HyperFrames (komposisi HTML, garis masa GSAP, tiada media luar) sudah ada dalam pekerja; tulis di sini apa yang anda mahu di atasnya. Anda boleh muat naik fail .md atau .txt.",
          "Your own instructions for motion videos (style, pace, colours, what must appear). The HyperFrames contract (HTML composition, GSAP timeline, no outside media) is already in the worker; write here what you want on top of it. You can upload a .md or .txt file.")}</p>
      </div>
      <TextArea rows={8} value={text} onChange={(e) => setText(e.target.value)} maxLength={SKILL_MAX} aria-label={t("Kemahiran motion", "Motion skill")}
        placeholder={t("Cth: Mula dengan hook 3 patah perkataan, satu nombor besar setiap babak, tutup dengan nama instrumen.", "E.g. Open with a three-word hook, one big number a scene, close on the instrument's name.")} />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={submit} disabled={busy || text.trim() === saved.trim()}><Save size={12} /> {t("Simpan", "Save")}</Button>
        <Button size="sm" variant="ghost" onClick={() => input.current?.click()}><Upload size={12} /> {t("Muat naik fail kemahiran", "Upload a skill file")}</Button>
        <input ref={input} type="file" accept=".md,.markdown,.txt,text/plain,text/markdown" className="hidden" onChange={take} data-motion-skill-file />
        <span className="ml-auto text-[11px] text-muted">{text.length} / {SKILL_MAX}</span>
      </div>
    </Card>
  );
}

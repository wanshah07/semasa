import { AMBIENTS, ambientOf } from "../lib/motion";
import { useLang } from "../lib/i18n";
import { Label } from "./ui/Field";

/* The ambient colour behind every scene of a film (Wan, 26 Oct 2026: "let me choose the background ambient colour in semasa"). */
export default function MotionAmbient({ value, onChange }) {
  const { t, lang } = useLang();
  const now = ambientOf(value);
  return (
    <div data-motion-ambient>
      <Label>{t("Warna ambient latar", "Ambient background colour")}</Label>
      <div className="flex flex-wrap gap-2">
        {AMBIENTS.map(([id, bm, en, hex]) => (
          <button key={id} type="button" onClick={() => onChange(id)} aria-pressed={now === id} data-ambient={id}
            className={`flex items-center gap-2 rounded-tile border px-3 py-1.5 text-sm ${now === id ? "border-accent bg-accent/10" : "border-line"}`}>
            <span className="inline-block h-5 w-5 rounded-tile border border-line" style={{ background: hex }} />{lang === "en" ? en : bm}
          </button>
        ))}
      </div>
    </div>
  );
}

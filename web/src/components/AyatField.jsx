import { useState } from "react";
import { BookOpen, Loader2, Trash2 } from "lucide-react";
import { ayatEdition, ayatLabel, ayatRef } from "../lib/compliance";
import { useLang } from "../lib/i18n";
import { fetchAyat } from "../lib/quran";
import Button from "./ui/Button";
import { Input } from "./ui/Field";

/* Ayat al-Quran on one slide (Wan, 16 Nov 2026: "make sure can write ayat al-Quran for reminder or under fatwa").
   The verse is NEVER typed: this field takes a reference (surah:ayat), "Ambil ayat" fetches the Arabic and the stream's
   translation from a published source (lib/quran.js), and both are shown read-only. Changing the reference clears the words
   and the tick, so what is stored always belongs to the reference beside it. The tick is Wan's own check that the verse
   fits the post; the scan blocks approval until it is set. */
export const AYAT_KEYS = ["ayat", "ayat_ar", "ayat_tr", "ayat_ed", "ayat_ok"];
const CLEAR = { ayat_ar: "", ayat_tr: "", ayat_ed: "", ayat_ok: "" };

export default function AyatField({ r, set, stream, locked, n, classic = false }) {
  const { t } = useLang();
  const [open, setOpen] = useState(() => !!r.ayat);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const ref = String(r.ayat || "").trim();
  const valid = !!ayatRef(ref), label = ayatLabel(ref);
  const ed = ayatEdition(stream);
  const fetched = !!(r.ayat_ar && r.ayat_tr);
  const wrongStream = fetched && !String(r.ayat_ed || "").startsWith(ed.id + "@");
  const take = async () => {
    setBusy(true); setErr("");
    try { set({ ...(await fetchAyat(ref, stream)), ayat_ok: "" }); }
    catch (e) { setErr(String(e?.message || e)); }
    finally { setBusy(false); }
  };
  if (!open && !ref) {
    return locked ? null : (
      <button type="button" onClick={() => setOpen(true)} className="mt-1.5 mr-3 inline-flex items-center gap-1 text-[11px] font-medium text-accent hover:underline">
        <BookOpen size={11} /> {t("Tambah ayat al-Quran", "Add an ayat al-Quran")}
      </button>
    );
  }
  return (
    <div className="mt-2 rounded-lg border border-line bg-paper/60 p-2.5" data-ayat-field>
      <div className="flex flex-wrap items-end gap-2">
        <label className="block min-w-0 flex-1">
          <span className="mb-1 block text-[11px] font-semibold text-muted">{t("Ayat al-Quran (surah:ayat)", "Ayat al-Quran (surah:ayat)")}</span>
          <Input value={r.ayat || ""} disabled={locked || busy} maxLength={11} inputMode="numeric" placeholder={t("cth: 2:168 atau 2:168-169", "e.g. 2:168 or 2:168-169")}
            aria-label={t("Rujukan ayat slaid {n}", "Slide {n} verse reference", { n })}
            onChange={(e) => { setErr(""); set({ ayat: e.target.value.replace(/[^\d:-]/g, ""), ...CLEAR }); }} />
        </label>
        {!locked && <Button type="button" size="sm" variant="soft" disabled={!valid || busy} onClick={take}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <BookOpen size={13} />} {fetched ? t("Ambil semula", "Fetch again") : t("Ambil ayat", "Fetch the verse")}
        </Button>}
        {!locked && <button type="button" aria-label={t("Buang ayat", "Remove the verse")} onClick={() => { setErr(""); set({ ayat: "", ...CLEAR }); setOpen(false); }}
          className="rounded p-2 text-muted hover:text-danger"><Trash2 size={13} /></button>}
      </div>
      {ref && !valid && <p className="mt-1.5 text-[11px] text-danger">{t("Ayat ini tidak wujud. Tulis surah:ayat, contohnya 2:168 (paling banyak 3 ayat, 2:168-170).",
        "This ayat does not exist. Write surah:ayat, for example 2:168 (at most 3 ayat, 2:168-170).")}</p>}
      {valid && !fetched && !err && <p className="mt-1.5 text-[11px] text-muted">{t("{label}. Tekan Ambil ayat: Semasa mengambil teks Arab dan terjemahan dari sumber yang diterbitkan. Ayat tidak pernah ditaip.",
        "{label}. Press Fetch the verse: Semasa takes the Arabic and the translation from a published source. A verse is never typed.", { label })}</p>}
      {err && <p className="mt-1.5 text-[11px] text-danger" role="alert">{err}</p>}
      {fetched && (
        <div className="mt-2">
          <p className="text-[12px] font-semibold text-ink">Surah {label}</p>
          <p dir="rtl" lang="ar" className="mt-1 text-right text-[22px] leading-[2.1] text-ink" style={{ fontFamily: '"Amiri Quran", "Scheherazade New", "Traditional Arabic", serif' }}>
            {String(r.ayat_ar).split("\n").join(" ۝ ")}
          </p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink">{String(r.ayat_tr).split("\n").join(" ")}</p>
          <p className="mt-1 text-[10px] text-muted">{ed.credit} · {String(r.ayat_ed || "").split("@")[1] || ""}</p>
          {wrongStream && <p className="mt-1.5 text-[11px] text-danger">{t("Terjemahan ini untuk aliran lain. Tekan Ambil semula.", "This translation is the other stream's. Press Fetch again.")}</p>}
          <label className="mt-2 flex items-start gap-2 text-[12px] text-ink">
            <input type="checkbox" className="mt-0.5" checked={r.ayat_ok === "1"} disabled={locked || wrongStream}
              onChange={(e) => set({ ayat_ok: e.target.checked ? "1" : "" })} />
            <span>{t("Saya sudah baca ayat dan terjemahan ini, dan ia sesuai dengan post ini.", "I have read this verse and its translation, and it fits this post.")}</span>
          </label>
          {classic && <p className="mt-1 text-[10px] text-muted">{t("Reka bentuk Klasik tidak boleh melukis tulisan Arab, jadi set ini dilukis dalam reka bentuk Grid.",
            "The Classic look cannot draw Arabic script, so this set is drawn in the Grid look.")}</p>}
          <p className="mt-1 text-[10px] text-muted">{t("Slaid ini dilukis sebagai kad ayat: teks Arab, terjemahan dan rujukan. Tajuk slaid jadi kepala kecil; baris lain jadi nota di bawah ayat.",
            "This slide is drawn as a verse card: the Arabic, the translation and the reference. The slide's title becomes a small heading; other lines become a note under the verse.")}</p>
        </div>
      )}
    </div>
  );
}

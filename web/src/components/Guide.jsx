import { slotsOf, PURGE_HOURS, LATE_GRACE_MIN } from "../lib/slots";
import { Modal } from "./ui/Field";

/* Studio's Panduan (argus rule 5: "include the layman guide in the system using ? icon"): what happens to a post and
   why it has or has not gone out, Bahasa Malaysia first and English under it. It reads its numbers (slots, rota, the
   switches) from the settings it is handed rather than restating them, so the guide and the page cannot drift apart.
   The publisher's clock is the one thing a page cannot read: it is .github/workflows/publish.yml, cron
   "20 22,3,11 * * *" UTC, kept here as the Malaysian times it means. Change both together. */
export const PUBLISH_RUNS_MYT = ["06:20", "11:20", "19:20"];

const DAYS_BM = ["Ahad", "Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu"];
const DAYS_EN = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function Pair({ bm, en }) {
  return (
    <div className="space-y-1">
      <p className="text-sm leading-relaxed text-ink">{bm}</p>
      <p className="text-[12.5px] leading-relaxed text-muted">{en}</p>
    </div>
  );
}

export default function Guide({ open, onClose, settings = {}, brand }) {
  const reg = slotsOf(brand, "regulab").join(" · ");
  const li = slotsOf(brand, "linkedin").join(" · ");
  const liDays = Array.isArray(brand?.linkedin?.days) && brand.linkedin.days.length ? brand.linkedin.days : null;
  const rota = [1, 2, 3, 4, 5, 6, 0].map((d) => {
    const v = (brand?.regulab?.schedule || {})[String(d)];
    const list = Array.isArray(v) ? v : v ? [v] : null;
    return { d, list };
  });
  const publishing = settings.publishing?.enabled === true;
  const auto = settings.autofill?.enabled === true;
  const runs = PUBLISH_RUNS_MYT.join(" · ");
  const sec = "space-y-2 border-t border-line pt-3";
  return (
    <Modal open={open} onClose={onClose} title="Panduan · Guide">
      <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">1 · Aliran kerja · The flow</h4>
          <Pair bm="Isu semasa, Regulatori atau Penerbitan Terkini → Jadikan idea → bot menulis draf dan gambar → anda semak di tab Post → Luluskan. Hanya post yang anda luluskan akan dihantar."
            en="Current issues, Regulatory or Latest publication → Make an idea → the bot writes the draft and pictures → you check it in Posts → Approve. Only posts you approve are ever sent." />
        </div>

        <div className={sec}>
          <h4 className="text-sm font-semibold">2 · Bila post keluar · When a post goes out</h4>
          <Pair bm={`Slot ws.regulab: ${reg} MYT. Slot LinkedIn: ${li} MYT${liDays ? `, pada ${liDays.map((d) => DAYS_BM[d]).join(", ")}` : ", setiap hari"}. Penerbit berjalan pada ${runs} MYT. Post yang lewat lebih ${LATE_GRACE_MIN} minit dari slotnya tidak dihantar: pindahkan ia (tab Post → Jadual → Pindah semua).`}
            en={`ws.regulab slots: ${reg} MYT. LinkedIn slots: ${li} MYT${liDays ? `, on ${liDays.map((d) => DAYS_EN[d]).join(", ")}` : ", every day"}. The publisher runs at ${runs} MYT. A post more than ${LATE_GRACE_MIN} minutes past its slot is never sent: move it (Posts → Schedule → Bump all).`} />
          <p className={`rounded-tile p-2 text-[12.5px] ${publishing ? "bg-ok/10 text-ok" : "bg-warn/10 text-ink"}`}>
            {publishing
              ? "Penerbitan HIDUP. · Publishing is ON."
              : "Penerbitan MATI: penerbit hanya merekod apa yang akan dihantar (cubaan kering). ws.regulab Studio masih penerbit sebenar. · Publishing is OFF: the publisher only records what it would send (a dry run). ws.regulab Studio is still the real publisher."}
          </p>
        </div>

        <div className={sec}>
          <h4 className="text-sm font-semibold">3 · Rota minggu · The weekly rota</h4>
          <ul className="grid gap-1 text-[12.5px] sm:grid-cols-2">
            {rota.map(({ d, list }) => (
              <li key={d}><b>{DAYS_BM[d]}</b> · {DAYS_EN[d]}: {list === null ? "semua domain · any domain" : list.length ? list.join(", ") : "tiada post · no posting"}</li>
            ))}
          </ul>
          <Pair bm="Kajian kes (kajian_kes) boleh masuk mana-mana hari yang ada post. Post di luar rota hanya diberi nota, tidak disekat."
            en="A case study (kajian_kes) may take any posting day. A post off the rota gets a note, never a block." />
        </div>

        <div className={sec}>
          <h4 className="text-sm font-semibold">4 · Draf yang tak kena · A draft that is not right</h4>
          <Pair bm="Tulis semula dengan nota: bot menulis semula perkataan sahaja, slaid dan gambar kekal. Tolak & ganti: bot menulis pengganti untuk slot yang sama, boleh guna gambar yang sama. Sejarah menyimpan setiap versi lama."
            en="Revise with a note: the bot rewrites the words only; slides and pictures stay. Reject & replace: the bot writes a replacement for the same slot and can reuse the same pictures. History keeps every older version." />
          <Pair bm={`Post yang ditolak dipadam sendiri ${PURGE_HOURS} jam selepas ditolak. Pulihkan sebelum itu jika perlu.`}
            en={`A rejected post deletes itself ${PURGE_HOURS} hours after it was rejected. Restore it before then if you need it.`} />
        </div>

        <div className={sec}>
          <h4 className="text-sm font-semibold">5 · Semakan · The checks</h4>
          <Pair bm="■ menyekat kelulusan (CTA, laman web dalam kapsyen, sumber media sosial, perkataan Indonesia, dan lain-lain). □ hanya nota. Tekan Betulkan → untuk terus ke tempatnya, atau Buang ayat seruan untuk membuang CTA dan laman web sekali klik."
            en="■ blocks approval (a CTA, a website in a caption, a social media source, an Indonesian word, and so on). □ is only a note. Press Fix → to jump to the place, or Remove ask to take out every CTA and website in one click." />
        </div>

        <div className={sec}>
          <h4 className="text-sm font-semibold">6 · Gambar · Pictures</h4>
          <Pair bm="Jana dengan AI, pilih dari Unsplash, atau muat naik gambar sendiri (dihoskan kekal, tiada kos). Slaid dan poster dilukis tanpa AI, dengan latar gambar anda sendiri dari Studio."
            en="Generate with AI, pick from Unsplash, or upload your own picture (hosted for good, no cost). Slides and posters are drawn without AI, on your own photographs from Studio." />
        </div>

        <div className={sec}>
          <h4 className="text-sm font-semibold">7 · Auto-isi slot kosong · Filling empty slots</h4>
          <p className={`rounded-tile p-2 text-[12.5px] ${auto ? "bg-accent/10 text-ink" : "bg-surface-2 text-muted"}`}>
            {auto
              ? `HIDUP: setiap larian bot menulis idea untuk slot kosong ${settings.autofill?.days_ahead || 3} hari ke depan. Semuanya draf. · ON: each bot run writes ideas for the empty slots of the next ${settings.autofill?.days_ahead || 3} days. All of them stay drafts.`
              : "MATI: tiada idea ditulis tanpa klik anda. Hidupkan di Tetapan. · OFF: no idea is written without your click. Switch it on in Settings."}
          </p>
        </div>
      </div>
    </Modal>
  );
}

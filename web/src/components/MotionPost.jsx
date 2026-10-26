import { useEffect, useMemo, useState } from "react";
import { CalendarX, CheckCircle2, Loader2, RefreshCw, Send } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { LANGUAGES, RESOLUTIONS, fmtBytes, remakeFields, streamOf } from "../lib/motion";
import { releaseSlots } from "../lib/releaseSlots";
import { sizeFor } from "../lib/platformFormat";
import { CHANNEL_LABEL, canQueue, channelsFor, filmFormat, pickPosition, postLang, queueArgs, startingCaptions } from "../lib/motionQueue";
import { clearPlan, myt, overrideCheck, slotsOf, takenSet } from "../lib/slots";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

const CHIPS = ["instagram", "facebook", "threads", "linkedin"];         // LinkedIn beside Threads: picking it makes the film a LinkedIn post
const streamOfChannel = (c) => (c === "linkedin" ? "linkedin" : "regulab");

/* A finished film to the platforms Wan picks (Wan, 26 Oct 2026: "allow me to choose which platform to post, so from the video can
   directly post or queue to post to platform, once post automatically the video compress and into post queue and remove from
   motion list"). One click writes the film as a video and a DRAFT post (semasa_queue_motion, supabase/051) on the chosen
   platforms, at the chosen date and slot, and the film leaves the Motion list. Approve & queue is Wan's own Approve click
   (taken only when the page's scan finds nothing blocking); Save as draft leaves it for the Posts tab. Either way the publisher
   scans the post again and sends the film as a video at its slot.
   Each platform's caption is set for it: the worker wrote one per platform with the film (in the film's language, inside that
   platform's limits). The film's format follows its platform (9:16 for ws.regulab, 1:1 for LinkedIn), and the version buttons make
   the film again in English, Malay or both (Wan, 26 Oct 2026: "tambah button english or malay or mixed version and redo").
   LinkedIn sits beside Threads (Wan, 26 Oct 2026: "boleh ada linkedn button sebelah threads, so bila aku click dan redo, boleh jadi
   post untuk linkedn"): the two voices are never mixed, so picking it chooses the other stream and Redo makes the film for it; until
   then there is nothing to queue. The slot can be one that is booked: the draft or approved post that holds it is let go of it, in the
   same transaction (supabase/054), and a link clears every booked slot of the stream. */

export default function MotionPost({ film, brand, indo, onQueued, onToast }) {
  const { t } = useLang();
  const all = channelsFor(film);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [post, setPost] = useState(null);                  // the idea's own draft: its words and rota domain are the start
  const [posts, setPosts] = useState([]);                  // what already holds a position, read fresh when this opens
  const [channels, setChannels] = useState(all);
  const [captions, setCaptions] = useState({});
  const [date, setDate] = useState("");
  const [slot, setSlot] = useState("");
  const [version, setVersion] = useState(film.language || "en");     // the language the film would be made again in
  const [streamPick, setStreamPick] = useState(streamOf(film.stream));     // the stream the film would be made again for
  const [redoing, setRedoing] = useState(false);
  const [override, setOverride] = useState(false);          // take a booked slot from its draft or approved holder
  const [clearing, setClearing] = useState(false);
  const stream = film.stream || "regulab";
  const format = filmFormat(film);

  // what holds a position now, read fresh (also after a slot is released)
  const loadHeld = async () => {
    const { data } = await supabase.from(TABLES.posts).select("id,hook,stream,status,date,slot").eq("stream", stream).neq("status", "rejected")
      .gte("date", myt().date);
    setPosts(data || []);
    return data || [];
  };

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    (async () => {
      setLoading(true);
      try {
        const [mine, held] = await Promise.all([
          film.idea_id ? supabase.from(TABLES.posts).select("id,text,citation,domain,created_at").eq("idea_id", film.idea_id)
            .neq("status", "rejected").order("created_at", { ascending: false }).limit(1) : Promise.resolve({ data: [] }),
          supabase.from(TABLES.posts).select("id,hook,stream,status,date,slot").eq("stream", stream).neq("status", "rejected")
            .gte("date", myt().date),
        ]);
        if (!live) return;
        const p = (mine.data || [])[0] || null;
        setPost(p);
        setPosts(held.data || []);
        setCaptions(startingCaptions({ film, post: p, channels: all }));
        const pos = pickPosition({ film, posts: held.data || [], brand, post: p });
        if (pos) { setDate(pos.date); setSlot(pos.slot); }
      } catch (e) { onToast?.(e.message || String(e), "error"); } finally { if (live) setLoading(false); }
    })();
    return () => { live = false; };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (c) => {
    const next = channels.includes(c) ? channels.filter((x) => x !== c) : all.filter((x) => channels.includes(x) || x === c);
    setChannels(next);
    setCaptions((cur) => ({ ...startingCaptions({ film, post, channels: all }), ...cur }));
  };
  const taken = useMemo(() => takenSet(posts, stream), [posts, stream]);
  const slots = slotsOf(brand, stream);
  const here = useMemo(() => (date && slot ? overrideCheck({ posts, stream, date, slot }) : { free: true, release: [], locked: [], ok: true }), [posts, stream, date, slot]);
  const useOverride = override && !here.free && here.ok;
  const ready = canQueue(film) && channels.length > 0 && date && slot && (here.free || useOverride);
  const plan = useMemo(() => clearPlan(posts, stream), [posts, stream]);
  useEffect(() => { setOverride(false); }, [date, slot]);
  const args = useMemo(() => (open && date && slot && channels.length
    ? queueArgs({ film, channels, captions, date, slot, brand, post, indo, override: useOverride }) : null), [open, film, channels, captions, date, slot, brand, post, indo, useOverride]);
  const hard = (args?.p_flags || []).filter((f) => f.hard);

  const queue = async (approve) => {
    if (!args) return;
    setBusy(true);
    try {
      const { error } = await supabase.rpc("semasa_queue_motion", { ...args, p_approve: !!approve && args.p_hard === 0, p_override: useOverride });
      if (error) throw new Error(errText(error));
      const where = { d: date, s: slot, c: channels.map((c) => CHANNEL_LABEL[c]).join(", ") };
      onToast?.(approve && args.p_hard === 0
        ? t("Diluluskan dan masuk giliran: disiarkan pada {d} {s} ({c}). Filem ini sudah keluar daripada senarai Motion.",
          "Approved and queued: it posts on {d} {s} ({c}). The film has left the Motion list.", where)
        : t("Masuk giliran Post sebagai draf pada {d} {s} ({c}). Luluskan di tab Post; filem ini sudah keluar daripada senarai Motion.",
          "In the Posts queue as a draft on {d} {s} ({c}). Approve it in the Posts tab; the film has left the Motion list.", where), "ok");
      onQueued?.();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(false); }
  };

  const clearAll = async () => {
    if (!plan.release.length) return;
    if (!window.confirm(t("Lepaskan {d} draf dan {a} post yang sudah diluluskan daripada slot mereka? Post yang diluluskan kembali menjadi draf dan perlu diluluskan semula. {k} post yang sudah dijadualkan atau disiarkan tidak disentuh.",
      "Release {d} draft(s) and {a} approved post(s) from their slots? An approved post goes back to draft and needs approving again. {k} post(s) already scheduled or sent are not touched.",
      { d: plan.drafts, a: plan.approved, k: plan.locked }))) return;
    setClearing(true);
    try {
      const { error, freed, stuck } = await releaseSlots(stream);
      if (error) throw new Error(errText(error));
      const held = await loadHeld();
      const pos = pickPosition({ film, posts: held, brand, post });
      if (pos) { setDate(pos.date); setSlot(pos.slot); }
      onToast?.(t("{f} slot dilepaskan{s}.", "{f} slot(s) released{s}.", { f: freed, s: stuck ? t("; {n} tidak dapat dilepaskan", "; {n} could not be released", { n: stuck }) : "" }), stuck ? "warn" : "ok");
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setClearing(false); }
  };
  const nextFree = () => {
    const pos = pickPosition({ film, posts, brand, post });
    if (pos) { setDate(pos.date); setSlot(pos.slot); }
  };

  // Redo: the same idea made again in the chosen language, in its platform's format, with fresh captions. It goes back to the worker
  // (a few minutes) and the film stays in the Motion list; this panel closes because the file it holds is being replaced.
  const redo = async () => {
    setRedoing(true);
    try {
      const { error } = await supabase.from(TABLES.motions).update(remakeFields(film, version, streamPick)).eq("id", film.id).is("queued_post_id", null);
      if (error) throw new Error(errText(error));
      const lang = (LANGUAGES.find(([k]) => k === version) || [])[1] || version;
      onToast?.(t("Dibuat semula untuk {p} dalam {l}, dalam saiz {s}: beberapa minit. Kapsyen ditulis semula bersama filem.",
        "Making it again for {p} in {l}, in the {s} size: a few minutes. The captions are written again with the film.",
        { p: streamPick === "linkedin" ? "LinkedIn" : "ws.regulab", l: lang, s: RESOLUTIONS[sizeFor(streamPick)]?.en?.split(" (")[0] }), "ok");
      setOpen(false);
      onQueued?.();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setRedoing(false); }
  };
  const switching = streamPick !== streamOf(film.stream);
  const changed = switching || version !== (film.language || "en");
  // a switch suggests the stream's own language (LinkedIn is Wan's English byline, ws.regulab speaks BM); the buttons still decide
  const pickStream = (s) => {
    setStreamPick(s);
    if (s === streamOf(film.stream)) setChannels(all);
    if (s === "linkedin" && version === "bm") setVersion("en"); else if (s === "regulab" && version === "en") setVersion("bm");
  };
  // a chip of the other stream's group switches the stream (nothing is queued until Redo has made the film for it); one of this
  // stream's own group toggles that platform
  const pickChip = (c) => {
    if (streamOfChannel(c) !== streamPick) return pickStream(streamOfChannel(c));
    if (!switching) toggle(c);
  };
  const chipOn = (c) => streamOfChannel(c) === streamPick && (switching || channels.includes(c));
  const versionName = (LANGUAGES.find(([k]) => k === version) || [])[1] || version;
  const written = Object.keys(film.captions || {}).length > 0;

  if (!canQueue(film)) return null;
  if (!open) {
    return <Button size="sm" variant="ghost" onClick={() => setOpen(true)} data-motion-post><Send size={12} /> {t("Siarkan / beratur", "Post / queue")}</Button>;
  }
  return (
    <div className="mt-3 w-full rounded-tile border border-line bg-surface-2 p-3" data-motion-post-panel>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{t("Siarkan filem ini", "Post this film")}</p>
        <button type="button" className="text-xs text-muted hover:text-ink" onClick={() => setOpen(false)}>{t("Tutup", "Close")}</button>
      </div>
      <p className="mt-1 text-xs text-muted">{t("Pilih platform, semak kapsyen dan slot. Filem dimampatkan, dimasukkan ke giliran Post dan keluar daripada senarai Motion. Lulus & beratur terus menjadualkannya; Simpan sebagai draf menunggu anda lulus di tab Post.",
        "Pick the platforms, check the captions and the slot. The film is compressed, put in the Posts queue and leaves the Motion list. Approve & queue schedules it at once; Save as draft waits for your approval in the Posts tab.")}</p>
      <div className="mt-3" data-motion-platforms>
        <Label hint={switching ? t("belum dibuat: tekan Buat semula", "not made yet: press Redo")
          : stream === "linkedin" ? t("aliran LinkedIn: suara Wan sendiri", "the LinkedIn stream: Wan's own voice") : t("aliran ws.regulab", "the ws.regulab stream")}>{t("Platform", "Platforms")}</Label>
        <div className="flex flex-wrap gap-2">
          {CHIPS.map((c) => (
            <label key={c} className={`inline-flex cursor-pointer items-center gap-2 rounded-pill px-3 py-1.5 text-xs ${chipOn(c) ? (switching ? "bg-warn/15 text-warn" : "bg-accent/15 text-accent") : "bg-surface text-muted"}`}
              data-motion-chip={c}>
              <input type="checkbox" checked={chipOn(c)} onChange={() => pickChip(c)} /> {CHANNEL_LABEL[c]}
            </label>
          ))}
        </div>
      </div>
      <div className="mt-3 rounded-tile border border-line bg-surface p-2" data-motion-version>
        <Label hint={t("filem dibuat semula, kapsyen ditulis semula bersamanya", "the film is made again and its captions are written again with it")}>{t("Versi", "Version")}</Label>
        <Segmented value={version} onChange={setVersion} options={LANGUAGES} />
        <div className="mt-2">
          <Button size="sm" variant={changed || !format.ok ? "primary" : "ghost"} disabled={redoing || (!changed && format.ok)} onClick={redo} data-motion-redo>
            {redoing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} {switching
              ? t("Buat semula untuk {p}: {l}", "Redo for {p}: {l}", { p: streamPick === "linkedin" ? "LinkedIn" : "ws.regulab", l: versionName })
              : t("Buat semula: {l}", "Redo: {l}", { l: versionName })}
          </Button>
        </div>
        {switching && <p className="mt-1.5 text-xs text-muted">{streamPick === "linkedin"
          ? t("Untuk LinkedIn: suara anda sendiri, saiz 1:1, ikon dan nama anda di kad penutup, dan kapsyen LinkedIn. Tekan Buat semula, kemudian pilih slot.",
            "For LinkedIn: your own voice, the 1:1 size, your icon and name on the closing card, and a LinkedIn caption. Press Redo, then pick the slot.")
          : t("Untuk ws.regulab: suara jenama, saiz 9:16, logo di kad penutup, dan kapsyen Instagram, Facebook dan Threads. Tekan Buat semula, kemudian pilih slot.",
            "For ws.regulab: the brand's voice, the 9:16 size, the logo on the closing card, and Instagram, Facebook and Threads captions. Press Redo, then pick the slot.")}</p>}
        {!format.ok && !switching && <p className="mt-1.5 text-xs text-warn">{t("Filem ini {a}, tetapi {p} paling sesuai dengan {b}. Buat semula menukarnya ke saiz platform.",
          "This film is {a}, but {p} takes {b} best. Redo changes it to the platform's size.",
          { a: RESOLUTIONS[film.resolution]?.en?.split(" (")[0] || film.resolution, b: RESOLUTIONS[format.want]?.en?.split(" (")[0], p: stream === "linkedin" ? "LinkedIn" : "ws.regulab" })}</p>}
        <p className="mt-1.5 text-[11px] text-muted">{format.ok ? t("Saiz filem: {s}, ikut platform.", "Film size: {s}, following the platform.", { s: RESOLUTIONS[format.want]?.en?.split(" (")[0] }) : ""}
          {" "}{written ? t("Kapsyen setiap platform ditulis bersama filem ini, dalam had platform itu.", "Each platform's caption was written with this film, inside that platform's limit.")
            : t("Filem ini dibuat sebelum kapsyen ditulis ikut platform: ia bermula daripada draf idea, dipotong ikut had setiap platform.", "This film was made before captions were written per platform: they start from the idea's draft, cut to each platform's limit.")}</p>
      </div>
      {switching ? null : loading ? <p className="mt-3 flex items-center gap-2 text-xs text-muted"><Loader2 size={12} className="animate-spin" /> {t("Membaca…", "Reading…")}</p> : (
        <div className="mt-3 space-y-3">
          {channels.map((c) => (
            <label key={c} className="block">
              <Label hint={`${(captions[c] || "").length} ${t("aksara", "chars")}`}>{t("Kapsyen", "Caption")} · {CHANNEL_LABEL[c]} · {film.language === "both" ? "BM + EN" : postLang(film).toUpperCase()}</Label>
              <TextArea rows={3} value={captions[c] || ""} onChange={(e) => setCaptions((cur) => ({ ...cur, [c]: e.target.value }))} />
            </label>
          ))}
          <div className="flex flex-wrap items-end gap-3">
            <label className="block"><Label>{t("Tarikh", "Date")}</Label>
              <Input type="date" value={date} min={myt().date} onChange={(e) => setDate(e.target.value)} className="!w-auto" /></label>
            <label className="block"><Label>{t("Slot (waktu Malaysia)", "Slot (Malaysia time)")}</Label>
              <Select value={slot} onChange={setSlot}
                options={slots.map((s) => [s, taken.has(`${date} ${s}`) ? `${s} · ${t("ditempah", "booked")}` : s])} /></label>
            <Button size="sm" variant="ghost" onClick={nextFree} data-motion-next-free>{t("Slot kosong seterusnya", "Next free slot")}</Button>
          </div>
          {date && slot && !here.free && here.ok && (
            <label className="flex items-start gap-2 rounded-tile border border-warn/40 bg-warn/10 p-2 text-xs" data-motion-override>
              <input type="checkbox" className="mt-0.5" checked={override} onChange={(e) => setOverride(e.target.checked)} />
              <span>{t("Slot ini ditempah oleh: {l}. Tanda untuk mengambilnya: post itu dilepaskan daripada slotnya{a}.",
                "This slot is booked by: {l}. Tick to take it: that post is let go of its slot{a}.",
                { l: here.release.map((p) => `${p.hook || String(p.id).slice(0, 8)} (${p.status})`).join(" · "),
                  a: here.release.some((p) => p.status === "approved") ? t(", dan kelulusannya ditarik balik (perlu diluluskan semula)", ", and its approval is withdrawn (it needs approving again)") : "" })}</span>
            </label>
          )}
          {date && slot && !here.ok && <p className="text-xs text-danger">{t("Slot ini dipegang oleh post yang sudah dijadualkan atau disiarkan: ia tidak boleh diambil. Pilih slot atau tarikh lain.",
            "This slot is held by a post that is already scheduled or sent, so it cannot be taken. Pick another slot or date.")}</p>}
          {!date && <p className="text-xs text-danger">{t("Tiada slot kosong dalam 60 hari: pilih tarikh sendiri.", "No free slot in 60 days: pick a date yourself.")}</p>}
          <button type="button" className="inline-flex items-center gap-1 text-[11px] text-muted underline hover:text-ink disabled:opacity-50" disabled={clearing || !plan.release.length} onClick={clearAll} data-motion-clear-slots>
            {clearing ? <Loader2 size={11} className="animate-spin" /> : <CalendarX size={11} />} {t("Kosongkan semua slot ditempah ({n})", "Clear all booked slots ({n})", { n: plan.release.length })}
          </button>
          {hard.length > 0 && (
            <ul className="space-y-0.5 rounded-tile bg-danger/10 p-2 text-xs text-danger">
              {hard.map((f, i) => <li key={i}><b>{f.where}</b> · {f.msg}</li>)}
              <li className="text-muted">{t("Boleh masuk giliran sebagai draf; betulkan di tab Post sebelum diluluskan.", "It can still be queued as a draft; fix it in the Posts tab before approving.")}</li>
            </ul>
          )}
          <p className="text-[11px] text-muted">
            {film.social_url
              ? t("Fail: salinan termampat {a} (asal {b}).", "File: the compressed copy, {a} (original {b}).", { a: fmtBytes(film.social_bytes), b: fmtBytes(film.bytes) })
              : t("Fail: video asal {b} (filem ini dibuat sebelum salinan termampat wujud; Buat semula jika mahu).", "File: the original video, {b} (made before the compressed copy existed; Make again if you want one).", { b: fmtBytes(film.bytes) })}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy || !ready || hard.length > 0} onClick={() => queue(true)} data-motion-approve
              title={hard.length ? t("Betulkan kapsyen dahulu", "Fix the captions first") : ""}>
              {busy ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />} {t("Lulus & beratur", "Approve & queue")}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy || !ready} onClick={() => queue(false)}>
              <Send size={12} /> {t("Simpan sebagai draf", "Save as draft")}
            </Button>
          </div>
          <p className="text-[11px] text-muted">{t("Lulus & beratur ialah klik lulus anda: filem disiarkan pada slot itu ke platform yang dipilih.",
            "Approve & queue is your own Approve click: the film posts at that slot on the platforms you picked.")}</p>
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { fmtBytes } from "../lib/motion";
import { CHANNEL_LABEL, canQueue, channelsFor, pickPosition, postLang, queueArgs, startingCaptions } from "../lib/motionQueue";
import { myt, slotsOf, takenSet } from "../lib/slots";
import Button from "./ui/Button";
import { Input, Label, Select, TextArea } from "./ui/Field";

/* A finished film to the platforms Wan picks (Wan, 26 Oct 2026: "allow me to choose which platform to post, so from the video can
   directly post or queue to post to platform, once post automatically the video compress and into post queue and remove from
   motion list"). One click writes the film as a video and a DRAFT post (semasa_queue_motion, supabase/051) on the chosen
   platforms, at the chosen date and slot, and the film leaves the Motion list. The gate stays Wan's Approve click in the Posts
   tab; the publisher scans the post again and sends the film as a video at its slot. */

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
  const stream = film.stream || "regulab";

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    (async () => {
      setLoading(true);
      try {
        const [mine, held] = await Promise.all([
          film.idea_id ? supabase.from(TABLES.posts).select("id,text,citation,domain,created_at").eq("idea_id", film.idea_id)
            .neq("status", "rejected").order("created_at", { ascending: false }).limit(1) : Promise.resolve({ data: [] }),
          supabase.from(TABLES.posts).select("id,stream,status,date,slot").eq("stream", stream).neq("status", "rejected")
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
  const ready = canQueue(film) && channels.length > 0 && date && slot && !taken.has(`${date} ${slot}`);
  const args = useMemo(() => (open && date && slot && channels.length
    ? queueArgs({ film, channels, captions, date, slot, brand, post, indo }) : null), [open, film, channels, captions, date, slot, brand, post, indo]);
  const hard = (args?.p_flags || []).filter((f) => f.hard);

  const queue = async () => {
    if (!args) return;
    setBusy(true);
    try {
      const { error } = await supabase.rpc("semasa_queue_motion", args);
      if (error) throw new Error(errText(error));
      onToast?.(t("Masuk giliran Post sebagai draf pada {d} {s} ({c}). Luluskan di tab Post; filem ini sudah keluar daripada senarai Motion.",
        "In the Posts queue as a draft on {d} {s} ({c}). Approve it in the Posts tab; the film has left the Motion list.",
        { d: date, s: slot, c: channels.map((c) => CHANNEL_LABEL[c]).join(", ") }), "ok");
      onQueued?.();
    } catch (e) { onToast?.(e.message || String(e), "error"); } finally { setBusy(false); }
  };

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
      <p className="mt-1 text-xs text-muted">{t("Pilih platform, semak kapsyen dan slot. Filem dimampatkan, dimasukkan ke giliran Post sebagai draf dan keluar daripada senarai Motion. Anda luluskan di tab Post.",
        "Pick the platforms, check the captions and the slot. The film is compressed, put in the Posts queue as a draft and leaves the Motion list. You approve it in the Posts tab.")}</p>
      {loading ? <p className="mt-3 flex items-center gap-2 text-xs text-muted"><Loader2 size={12} className="animate-spin" /> {t("Membaca…", "Reading…")}</p> : (
        <div className="mt-3 space-y-3">
          <div>
            <Label hint={stream === "linkedin" ? t("aliran LinkedIn: suara Wan sendiri", "the LinkedIn stream: Wan's own voice") : t("aliran ws.regulab", "the ws.regulab stream")}>{t("Platform", "Platforms")}</Label>
            <div className="flex flex-wrap gap-2">
              {all.map((c) => (
                <label key={c} className={`inline-flex cursor-pointer items-center gap-2 rounded-pill px-3 py-1.5 text-xs ${channels.includes(c) ? "bg-accent/15 text-accent" : "bg-surface text-muted"}`}>
                  <input type="checkbox" checked={channels.includes(c)} onChange={() => toggle(c)} /> {CHANNEL_LABEL[c]}
                </label>
              ))}
            </div>
          </div>
          {channels.map((c) => (
            <label key={c} className="block">
              <Label hint={`${(captions[c] || "").length} ${t("aksara", "chars")}`}>{t("Kapsyen", "Caption")} · {CHANNEL_LABEL[c]} · {postLang(film).toUpperCase()}</Label>
              <TextArea rows={3} value={captions[c] || ""} onChange={(e) => setCaptions((cur) => ({ ...cur, [c]: e.target.value }))} />
            </label>
          ))}
          <div className="flex flex-wrap items-end gap-3">
            <label className="block"><Label>{t("Tarikh", "Date")}</Label>
              <Input type="date" value={date} min={myt().date} onChange={(e) => setDate(e.target.value)} className="!w-auto" /></label>
            <label className="block"><Label>{t("Slot (waktu Malaysia)", "Slot (Malaysia time)")}</Label>
              <Select value={slot} onChange={setSlot}
                options={slots.map((s) => [s, taken.has(`${date} ${s}`) ? `${s} · ${t("diambil", "taken")}` : s])} /></label>
          </div>
          {date && slot && taken.has(`${date} ${slot}`) && <p className="text-xs text-danger">{t("Slot ini sudah dipegang post lain: pilih slot atau tarikh lain.", "This slot is held by another post: pick another slot or date.")}</p>}
          {!date && <p className="text-xs text-danger">{t("Tiada slot kosong dalam 60 hari: pilih tarikh sendiri.", "No free slot in 60 days: pick a date yourself.")}</p>}
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
          <Button size="sm" disabled={busy || !ready} onClick={queue}>
            {busy ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} {t("Masukkan ke giliran siaran", "Put in the post queue")}
          </Button>
        </div>
      )}
    </div>
  );
}

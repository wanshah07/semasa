import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CalendarClock, Check, Eraser, ImagePlus, Info, RotateCcw, Save, Trash2, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { LIMITS, charLen, hardCount, normaliseSlides, platformsFor, scan, scanMedia, stripPromo } from "../lib/compliance";
import { dueMs, nextFreeSlot, refOf, slotsOf, takenSet } from "../lib/slots";
import { withDecision } from "../lib/workflow";
import PostWorkflow from "./PostWorkflow";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";
import SlidesEditor, { fromRows, toRows } from "./SlidesEditor";
import { GROUNDS, bgUrlOf, defaultGround } from "../lib/cards/library";
import { isStudioLook } from "../lib/cards/studio";
import { UnsplashCredit, UnsplashResults, UnsplashSearch, isUnsplash } from "./Unsplash";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

const PLAT_LABEL = { instagram: "Instagram", facebook: "Facebook", threads: "Threads", linkedin: "LinkedIn" };

/* One post, the way Studio's drawer worked: the words per language and platform, the source,
   the position, the pictures, and the same checks the publisher will run — live, as you type.
   Approve is offered only when nothing blocks. Changing an approved post sends it back to
   draft (the database does that, not this page), so what was approved is what goes out. */
export default function PostEditor({ post, posts = [], mediaById, mediaRows, log, brand, user, indoExtra, onToast, onChanged, onClose }) {
  const { t } = useLang();
  const [text, setText] = useState(post.text || {});
  const [lang, setLang] = useState(post.lang || (post.stream === "linkedin" ? "en" : "bm"));
  const [view, setView] = useState(post.lang || (post.stream === "linkedin" ? "en" : "bm"));
  const [citation, setCitation] = useState(post.citation || "");
  const [date, setDate] = useState(post.date || "");
  const [slot, setSlot] = useState(post.slot || "");
  const [mediaIds, setMediaIds] = useState(post.media_ids || []);
  const [slideRows, setSlideRows] = useState(toRows(post.slides));
  // the set's background: the last drawing's, else Studio's default for this domain or angle (Wan's own photographs)
  const [bg, setBg] = useState(() => (mediaRows.filter((m) => m.mode === "slides" && m.post_id === post.id && !m.meta?.design)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0]?.meta?.bg) || "none");
  // the carousel's look: the one its last drawing used, Semasa's own drawing when there is none
  const lastLook = () => (mediaRows.filter((m) => m.mode === "slides" && m.post_id === post.id && !m.meta?.design)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))[0]?.meta?.look) || "classic";
  const [look, setLook] = useState(lastLook);
  const [lookBlocked, setLookBlocked] = useState(null);
  const [busy, setBusy] = useState(false);
  const [newPic, setNewPic] = useState("");

  // Reset only when this post changes in the database (another save, the worker attaching slides), never on a poll
  // that hands back the same row: that used to wipe an unsaved caption every 90 seconds.
  // A change to the SAME post takes a field from the database only where nothing was typed into it since the last
  // copy: the worker attaching a picture or slides bumps updated_at, and that used to throw away an unsaved caption.
  // New pictures are added to the ones being edited, so an attach is never lost either.
  const base = useRef(null);
  useEffect(() => {
    const l = post.lang || (post.stream === "linkedin" ? "en" : "bm");
    const fresh = { text: post.text || {}, lang: l, citation: post.citation || "", date: post.date || "",
      slot: post.slot || "", mediaIds: post.media_ids || [], slideRows: toRows(post.slides) };
    const old = base.current;
    base.current = { id: post.id, ...fresh };
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const take = (k, setter, now) => { if (!old || old.id !== post.id || same(now, old[k])) setter(fresh[k]); };
    take("text", setText, text); take("citation", setCitation, citation);
    take("date", setDate, date); take("slot", setSlot, slot); take("slideRows", setSlideRows, slideRows);
    if (!old || old.id !== post.id || same(lang, old.lang)) { setLang(l); setView(l); }
    if (!old || old.id !== post.id || same(mediaIds, old.mediaIds)) setMediaIds(fresh.mediaIds);
    else {
      const added = fresh.mediaIds.filter((id) => !old.mediaIds.includes(id) && !mediaIds.includes(id));
      if (added.length) setMediaIds((ids) => [...ids, ...added]);
    }
  }, [post.id, post.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setLook(lastLook()); }, [post.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const reg = brand.regulab;
  const plats = platformsFor(post.stream);
  const locked = post.status === "scheduled" || post.status === "posted";
  const chosen = mediaIds.map((id) => mediaById[id]).filter(Boolean);
  const candidates = mediaRows.filter((m) => m.status === "done" && m.generated_media_url && !mediaIds.includes(m.id)
    && m.mode !== "slides" && (m.post_id === post.id || (post.idea_id && m.idea_id === post.idea_id)));
  const pending = mediaRows.filter((m) => (m.post_id === post.id) && m.mode !== "slides" && !isUnsplash(m)
    && (m.status === "pending" || m.status === "processing"));
  // this post's Unsplash searches still waiting for a pick (a picked one is an ordinary candidate picture)
  const unsplashOpen = mediaRows.filter((m) => m.post_id === post.id && isUnsplash(m) && !m.generated_media_url)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 2);
  // `slides` exists once supabase/006_slides.sql has run; before that the editor says so and saves nothing new
  const hasSlides = post.slides !== undefined;
  const slides = normaliseSlides(fromRows(slideRows));
  const slideJobs = mediaRows.filter((m) => m.mode === "slides" && m.post_id === post.id && !m.meta?.design)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const pictures = mediaRows.filter((m) => m.post_id === post.id && m.type === "image" && m.mode !== "slides" && m.status === "done"
    && m.generated_media_url);
  // what the look preview draws on: the same picture the worker will fetch for this background choice
  const firstPicture = pictures.slice().sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))[0];
  const resolveBg = (token) => bgUrlOf(token, { postImage: firstPicture?.generated_media_url || "",
    mediaUrl: (id) => pictures.find((m) => m.id === id)?.generated_media_url || mediaById[id]?.generated_media_url || "" });
  const bgUrl = resolveBg(bg);
  const eyebrow = post.stream === "linkedin" ? (brand.linkedin?.angles?.[post.angle] || "") : (brand.regulab?.domains?.[post.domain] || "");
  const bgOptions = [["none", t("Kertas", "Paper")], ["post_image", t("Gambar pertama post", "Post's first picture")],
    ...pictures.map((m, i) => [m.id, `${t("Gambar {n}", "Picture {n}", { n: i + 1 })}${m.prompt ? `: ${m.prompt.slice(0, 28)}` : ""}`]),
    ...(bg && !["none", "post_image"].includes(bg) && !bg.startsWith("lib:") && !pictures.some((m) => m.id === bg)
      ? [[bg, t("Latar lukisan terakhir", "The last drawing's background")]] : []),
    ...GROUNDS.map((g) => [`lib:${g.k}`, `${t("Foto Wan", "Wan's photo")}: ${g.name}`])];

  const current = { ...post, text, lang, citation, date: date || null, slot: slot || null, media_ids: mediaIds,
    ...(hasSlides ? { slides } : {}),
    media: chosen.filter((m) => m.status === "done").map(scanMedia) };
  const flags = useMemo(() => scan(current, reg, reg.schedule, indoExtra), [JSON.stringify(current), reg, indoExtra]); // eslint-disable-line
  const [mediaState, setMediaState] = useState({ key: "", rows: [] });
  const idsKey = mediaIds.join(",");
  const rowsSig = mediaIds.map((id) => `${id}:${mediaById[id]?.status || "?"}`).join(",");
  useEffect(() => {
    let live = true;
    if (!mediaIds.length || !supabase) { setMediaState({ key: idsKey, rows: [] }); return undefined; }
    supabase.from(TABLES.media).select("id,status,generated_media_url").in("id", mediaIds)
      .then(({ data, error }) => { if (live && !error) setMediaState({ key: idsKey, rows: data || [] }); });
    return () => { live = false; };
  }, [idsKey, rowsSig]); // eslint-disable-line react-hooks/exhaustive-deps
  const checked = mediaState.key === idsKey;
  const gone = checked ? mediaIds.filter((id) => !mediaState.rows.some((m) => m.id === id)) : [];
  const unready = checked ? mediaState.rows.filter((m) => mediaIds.includes(m.id) && (m.status !== "done" || !m.generated_media_url)) : [];
  const hard = hardCount(flags);
  // a slot more than 45 minutes gone is never sent (publisher.py LATE_GRACE): approving it would only read "✓ checks
  // passed" while nothing goes out. A page-only block, not saved in hard_flags, because it depends on the clock.
  const past = ["draft", "approved", "rejected"].includes(post.status) && !!(date && slot)
    && Date.parse(`${date}T${slot}:00+08:00`) < Date.now() - 45 * 60_000;
  const shownFlags = !date || !slot
    ? [...flags, { hard: false, where: t("Kedudukan", "Position"), msg: t("belum ada tarikh dan slot: penerbit melangkau post tanpanya",
      "no date and slot yet: the publisher skips a post without one") }]
    : past ? [...flags, { hard: true, where: t("Kedudukan", "Position"), msg: t("slot ini sudah lepas: penerbit tidak menghantar post yang lewat lebih 45 minit. Pilih tarikh atau slot baharu.",
      "this slot has passed: the publisher never sends a post more than 45 minutes late. Pick a new date or slot.") }]
      : [...flags];
  // the publisher refuses a post whose attached picture was deleted or never finished (publisher.py not_ready/gone);
  // read from the database, because the Media list holds only the newest rows
  if (gone.length) shownFlags.push({ hard: true, where: t("Gambar", "Pictures"), msg: t("{n} gambar yang dilampirkan sudah dipadam: buang daripada post ini",
    "{n} attached picture(s) were deleted: remove them from this post", { n: gone.length }) });
  if (unready.length) shownFlags.push({ hard: true, where: t("Gambar", "Pictures"), msg: t("{n} gambar yang dilampirkan belum siap atau gagal",
    "{n} attached picture(s) are not finished or failed", { n: unready.length }) });
  const blocking = hard + (past ? 1 : 0) + (gone.length ? 1 : 0) + (unready.length ? 1 : 0);

  function setCaption(lg, plat, v) {
    setText((prev) => ({ ...prev, [lg]: { ...(prev[lg] || {}), [plat]: v } }));
  }

  async function write(patch, msg) {
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.posts).update(patch).eq("id", post.id).select().single();
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    if (post.status === "approved" && patch.status === undefined && data.status === "draft") {
      onToast(t("Disimpan. Post ini diubah selepas diluluskan, jadi ia kembali ke draf: luluskan semula.",
        "Saved. This post was changed after approval, so it went back to draft: approve it again."), "warn");
    } else onToast(msg, "ok");
    onChanged();
  }

  const content = () => ({ text, lang, citation, date: date || null, slot: slot || null, media_ids: mediaIds,
    ...(hasSlides ? { slides } : {}), flags, hard_flags: hard });
  // the decision record rides on the same write, only once 021 has added the column (a row read before it has no key)
  const decided = (action, note = "") => ("decisions" in post ? { decisions: withDecision(post, action, note) } : {});
  const dirty = JSON.stringify(text) !== JSON.stringify(post.text || {}) || citation !== (post.citation || "")
    || (date || "") !== (post.date || "") || (slot || "") !== (post.slot || "")
    || JSON.stringify(mediaIds) !== JSON.stringify(post.media_ids || []);

  // Restore goes back on its own slot while that is still ahead and free, else on the next free one for the stream
  // (Studio's restoreDraft put two posts on one slot until it asked claimSlot; the slot is re-read from the database
  // first, since the list on screen can be a poll behind)
  async function restore() {
    setBusy(true);
    const { data: live, error } = await supabase.from(TABLES.posts).select("id,stream,status,date,slot")
      .eq("stream", post.stream || "regulab").neq("status", "rejected").gte("date", new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10));
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    const all = live || posts;
    const ownFree = post.date && post.slot && dueMs(post.date, post.slot) > Date.now() + 30 * 60_000
      && !takenSet(all, post.stream || "regulab", post.id).has(`${post.date} ${post.slot}`);
    const pos = ownFree ? { date: post.date, slot: post.slot }
      : nextFreeSlot({ posts: all, brand, stream: post.stream || "regulab", domain: post.domain, skipId: post.id, fromDate: post.date });
    const moved = pos && (pos.date !== post.date || pos.slot !== post.slot);
    await write({ status: "draft", ...(pos ? { date: pos.date, slot: pos.slot } : {}),
      ...decided("restored", moved ? `from ${post.date || "-"} ${post.slot || ""}` : "") },
    moved ? t("Dipulihkan ke draf, dipindah ke {d} {s} (slot asal sudah lepas atau diambil).", "Restored to draft, moved to {d} {s} (its slot had passed or was taken).", { d: pos.date, s: pos.slot })
      : pos ? t("Dipulihkan ke draf.", "Restored to draft.") : t("Dipulihkan ke draf. Tiada slot kosong dalam 60 hari: pilih tarikh.", "Restored to draft. No free slot in 60 days: pick a date."));
  }

  // Studio's "Fix →": from a flag to the field it is about (the other language's caption opens that language first)
  function fixTarget(where) {
    const w = String(where || "");
    const plat = (w.match(/\((instagram|facebook|threads|linkedin)\)/) || [])[1];
    if (plat) return { id: `cap-${post.id}-${plat}`, other: /variant/.test(w) };
    if (/^(Slide|Carousel|Slides|Sources)/.test(w)) return { id: `slides-${post.id}` };
    if (/^(Position|Kedudukan|Rota)/.test(w)) return { id: `date-${post.id}` };
    if (/^(Pictures|Gambar|Post|Design)/.test(w)) return { id: `pics-${post.id}` };
    return null;
  }
  function jump(where) {
    const to = fixTarget(where);
    if (!to) return;
    if (to.other) setView(lang === "bm" ? "en" : "bm"); else if (/^cap-/.test(to.id)) setView(lang);
    window.setTimeout(() => {
      const el = document.getElementById(to.id);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      if (el.focus && /^(cap|date)-/.test(to.id)) el.focus({ preventScroll: true });
    }, 60);
  }

  function takeNextFree() {
    const pos = nextFreeSlot({ posts, brand, stream: post.stream || "regulab", domain: post.domain, skipId: post.id });
    if (!pos) return onToast(t("Tiada slot kosong dalam 60 hari.", "No free slot in the next 60 days."), "warn");
    setDate(pos.date); setSlot(pos.slot);
    onToast(t("{d} {s} dipilih. Tekan Simpan.", "{d} {s} chosen. Press Save.", { d: pos.date, s: pos.slot }), "info");
  }

  // the ask and the brand's website out of every caption, in one click; the words stay on screen until Save
  const promo = (() => {
    let n = 0;
    for (const lg of Object.keys(text || {})) for (const v of Object.values(text[lg] || {})) n += stripPromo(v, reg).removed.length;
    return n;
  })();
  function stripAll() {
    const out = {};
    for (const [lg, byPlat] of Object.entries(text || {})) {
      out[lg] = {};
      for (const [p, v] of Object.entries(byPlat || {})) out[lg][p] = stripPromo(v, reg).text;
    }
    setText(out);
    onToast(t("{n} ayat seruan atau laman web dibuang. Semak, kemudian Simpan.", "{n} ask or website sentence(s) removed. Check, then Save.", { n: promo }), "info");
  }

  async function renderSlides() {
    if (!slides.length) return onToast(t("Tulis sekurang-kurangnya satu slaid.", "Write at least one slide."), "warn");
    if (lookBlocked) return onToast(lookBlocked === "photo"
      ? t("Reka bentuk Foto perlu gambar latar.", "The Photo design needs a background picture.")
      : t("Ada slaid terlalu penuh untuk reka bentuk ini.", "A slide is too full for this design."), "warn");
    setBusy(true);
    const saved = await supabase.from(TABLES.posts).update(content()).eq("id", post.id).select().single();
    if (saved.error) { setBusy(false); return onToast(errText(saved.error), "danger"); }
    const { error } = await supabase.from(TABLES.media).insert({
      mode: "slides", type: "image", prompt: "", status: "pending", created_by: user.id,
      post_id: post.id, idea_id: post.idea_id,
      meta: { flow: "B", slides, stream: post.stream, citation, domain: post.domain, angle: post.angle, bg, look },
    });
    setBusy(false);
    if (error) {
      return onToast(/mode_check/.test(errText(error))
        ? t("Slaid belum disediakan dalam pangkalan data: jalankan supabase/006_slides.sql sekali.",
          "Slides are not set up in the database yet: run supabase/006_slides.sql once.") : errText(error), "danger");
    }
    onToast(post.status === "approved" && saved.data.status === "draft"
      ? t("Disimpan (post kembali ke draf) dan slaid dalam giliran untuk dilukis.",
        "Saved (post went back to draft) and slides queued for drawing.")
      : t("Disimpan. Slaid dalam giliran untuk dilukis.", "Saved. Slides queued for drawing."), "ok");
    onChanged();
  }

  // one carousel per post: a set chosen here replaces the post's earlier set, in the same place
  function chooseSet(id) {
    // the carousel's own sets only: a Design-tab poster is also mode "slides" and must stay on the post
    const old = new Set(mediaRows.filter((m) => m.mode === "slides" && !m.meta?.design).map((m) => m.id));
    setMediaIds((ids) => {
      const at = Math.max(0, ids.findIndex((x) => old.has(x)));
      const kept = ids.filter((x) => !old.has(x));
      kept.splice(Math.min(at, kept.length), 0, id);
      return kept;
    });
    onToast(t("Set slaid dipilih. Tekan Simpan.", "Slide set chosen. Press Save."), "info");
  }

  async function queuePicture() {
    if (!newPic.trim() || busy) return;
    setBusy(true);                      // a double click queued two jobs
    const { error } = await supabase.from(TABLES.media).insert({
      mode: "prompt", type: "image", prompt: newPic.trim(), status: "pending", created_by: user.id,
      post_id: post.id, idea_id: post.idea_id, meta: { alt: "", flow: "B" },
    });
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    setNewPic(""); onToast(t("Gambar baharu dalam giliran.", "New picture queued."), "ok"); onChanged();
  }

  const slots = slotsOf(brand, post.stream || "regulab");
  const clash = date && slot ? posts.filter((p) => p.id !== post.id && (p.stream || "regulab") === (post.stream || "regulab")
    && p.status !== "rejected" && p.date === date && p.slot === slot) : [];
  const myLog = log.filter((l) => l.post_id === post.id).slice(0, 12);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={view} onChange={setView} options={[["bm", "BM"], ["en", "EN"]]} />
        <span className="text-xs text-muted">{t("Bahasa yang dihantar:", "Language sent:")}</span>
        <Select value={lang} onChange={setLang} options={[["bm", "BM"], ["en", "EN"]]} disabled={locked} aria-label={t("Bahasa dihantar", "Language sent")} />
        {onClose && <button type="button" onClick={onClose} className="ml-auto text-sm text-muted hover:text-ink" aria-label={t("Tutup", "Close")}><X size={16} /></button>}
      </div>

      {plats.map((p) => {
        const v = ((text[view] || {})[p]) || "";
        const lim = (LIMITS[post.stream] || {})[p];
        return (
          <label key={p} className="block">
            <Label hint={`${charLen(v)}${lim ? ` / ${lim.max}` : ""} ${t("aksara", "characters")}${
              view !== lang ? ` · ${t("tidak dihantar", "not sent")}` : ""}`}>{PLAT_LABEL[p]}</Label>
            <TextArea id={`cap-${post.id}-${p}`} rows={p === "threads" ? 4 : 7} value={v} disabled={locked} onChange={(e) => setCaption(view, p, e.target.value)}
              className={lim && charLen(v) > lim.max ? "border-danger" : ""} />
          </label>
        );
      })}

      <label className="block"><Label hint={t("instrumen / pengawal selia, bukan portal berita", "instrument / regulator, not a news portal")}>
        {t("Sumber", "Source")}</Label>
        <Input value={citation} disabled={locked} onChange={(e) => setCitation(e.target.value)} /></label>

      <div className="flex flex-wrap items-end gap-3">
        <label><Label>{t("Tarikh (MYT)", "Date (MYT)")}</Label><Input id={`date-${post.id}`} type="date" value={date || ""} disabled={locked} onChange={(e) => setDate(e.target.value)} className="w-44" /></label>
        <label><Label>Slot</Label><Select value={slot && !slots.includes(slot) ? "other" : slot || ""} disabled={locked}
          onChange={(v) => setSlot(v === "other" ? (slot && !slots.includes(slot) ? slot : "10:00") : v)}
          options={[["", "—"], ...slots.map((s) => [s, s]), ["other", t("Masa lain…", "Another time…")]]} /></label>
        {slot && !slots.includes(slot) && (
          <label><Label>{t("Masa (MYT)", "Time (MYT)")}</Label><Input type="time" value={slot} disabled={locked} onChange={(e) => setSlot(e.target.value)} className="w-32" /></label>
        )}
        {!locked && <Button type="button" size="sm" variant="ghost" onClick={takeNextFree}><CalendarClock size={12} /> {t("Slot kosong seterusnya", "Next free slot")}</Button>}
        {date && slot && <span className="self-center text-[11px] text-muted">{refOf({ ...post, date, slot }, brand)}</span>}
      </div>
      {clash.length > 0 && !locked && (
        <p className="-mt-2 text-[12px] text-warn">{t("Slot ini juga dipegang oleh: {h}. Dua post pada satu slot akan keluar serentak.",
          "This slot is also held by: {h}. Two posts on one slot go out together.", { h: clash.map((p) => p.hook || p.id.slice(0, 8)).join(" · ") })}</p>
      )}

      <div id={`pics-${post.id}`}>
        <Label hint={t("urutan = urutan dihantar", "order = order sent")}>{t("Gambar", "Pictures")}</Label>
        <div className="flex flex-wrap gap-2">
          {chosen.map((m) => (
            <span key={m.id} className="relative">
              {m.mode === "slides" && <span className="absolute bottom-1 left-1 z-10 rounded bg-ink/80 px-1 text-[10px] text-bg">{t("{n} slaid", ["{n} slide", "{n} slides"], { n: m.meta?.count || "?" })}</span>}
              {m.type === "video"
                ? <video src={m.generated_media_url} className="h-36 w-36 rounded-tile bg-black object-cover sm:h-32 sm:w-32 lg:h-24 lg:w-24" muted />
                : <img src={m.generated_media_url || m.reference_url} alt={m.meta?.alt || ""} className="h-36 w-36 rounded-tile object-cover sm:h-32 sm:w-32 lg:h-24 lg:w-24" />}
              {!locked && <button type="button" aria-label={t("Buang gambar", "Remove picture")} onClick={() => setMediaIds((ids) => ids.filter((x) => x !== m.id))}
                className="absolute -right-1 -top-1 rounded-full bg-ink p-0.5 text-bg"><X size={11} /></button>}
            </span>
          ))}
          {!chosen.length && <span className="text-xs text-muted">{t("Belum ada gambar dipilih.", "No picture chosen yet.")}</span>}
        </div>
        {!locked && candidates.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-muted">{t("Tambah:", "Add:")}</span>
            {candidates.map((m) => (
              <button type="button" key={m.id} onClick={() => setMediaIds((ids) => [...ids, m.id])} title={m.prompt}>
                {m.type === "video"
                  ? <video src={m.generated_media_url} className="h-24 w-24 rounded-tile bg-black object-cover opacity-80 hover:opacity-100 lg:h-14 lg:w-14" muted />
                  : <img src={m.generated_media_url} alt="" className="h-24 w-24 rounded-tile object-cover opacity-80 hover:opacity-100 lg:h-14 lg:w-14" />}
              </button>
            ))}
          </div>
        )}
        {pending.length > 0 && <p className="mt-1 text-[11px] text-muted">
          {t("{n} gambar sedang dijana; ia masuk ke sini sendiri selagi post ini draf.",
            "{n} pictures being generated; they come in here by themselves while this post is a draft.", { n: pending.length })}</p>}
        {!locked && (
          <div className="mt-2 flex gap-2">
            <Input value={newPic} onChange={(e) => setNewPic(e.target.value)} placeholder={t("Jana gambar lain: terangkan gambarnya…", "Generate another picture: describe it…")} />
            <Button type="button" size="sm" variant="soft" onClick={queuePicture} disabled={!newPic.trim() || busy}><ImagePlus size={12} /> {t("Jana", "Generate")}</Button>
          </div>
        )}
        {!locked && (
          <div className="mt-2">
            <UnsplashSearch user={user} postId={post.id} ideaId={post.idea_id} stream={post.stream} onToast={onToast} onQueued={onChanged} compact />
            {unsplashOpen.map((m) => (
              <div key={m.id} className="mt-2 rounded-tile border border-line"><UnsplashResults row={m} onToast={onToast} onPicked={onChanged} /></div>
            ))}
          </div>
        )}
        {chosen.filter(isUnsplash).map((m) => <UnsplashCredit key={m.id} row={m} className="mt-1" />)}
      </div>

      {hasSlides ? (
        <div id={`slides-${post.id}`}><SlidesEditor post={post} rows={slideRows} setRows={setSlideRows} locked={locked} jobs={slideJobs}
          attachedIds={mediaIds} bg={bg} setBg={setBg} bgOptions={bgOptions} busy={busy}
          onRender={renderSlides} onUse={chooseSet} look={look}
          setLook={(k) => { setLook(k); if (isStudioLook(k) && bg === "none" && defaultGround(post)) setBg(defaultGround(post)); }}
          preview={{ eyebrow, citation, bgUrl, brand: reg }} blocked={lookBlocked} setBlocked={setLookBlocked} resolveBg={resolveBg}
          onToast={onToast} captionPost={{ stream: post.stream, hook: post.hook || "",
            caption: ((text[lang] || {})[post.stream === "linkedin" ? "linkedin" : "instagram"]) || ((text[lang] || {}).facebook) || "" }} /></div>
      ) : (
        <p className="rounded-tile border border-dashed border-line p-3 text-[12px] text-muted">
          {t("Slaid carousel belum tersedia: jalankan", "Carousel slides are not available yet: run")} <code>supabase/006_slides.sql</code>{" "}
          {t("sekali di Supabase SQL editor.", "once in the Supabase SQL editor.")}
        </p>
      )}

      <div className="rounded-tile border border-line p-3">
        <p className={`flex items-center gap-1.5 text-sm font-medium ${blocking ? "text-danger" : "text-ok"}`}>
          {blocking ? <AlertTriangle size={14} /> : <Check size={14} />}
          {blocking ? t("{n} perkara menyekat kelulusan", ["{n} item blocking approval", "{n} items blocking approval"], { n: blocking }) : t("Semakan lulus", "Checks passed")}
        </p>
        <ul className="mt-2 space-y-1 text-[12px]">
          {shownFlags.map((f, i) => (
            <li key={i} className={f.hard ? "text-danger" : "text-muted"}>
              {f.hard ? "■" : "□"} <b>{f.where}</b>: {f.msg}
              {!locked && fixTarget(f.where) && <button type="button" className="ml-1 underline decoration-dotted hover:text-ink"
                onClick={() => jump(f.where)}>{t("Betulkan →", "Fix →")}</button>}
            </li>
          ))}
        </ul>
        {promo > 0 && !locked && <Button size="sm" variant="soft" className="mt-2 mr-2" onClick={stripAll}>
          <Eraser size={12} /> {t("Buang {n} ayat seruan / laman web", "Remove {n} ask / website sentence(s)", { n: promo })}</Button>}
        {gone.length > 0 && !locked && <Button size="sm" variant="soft" className="mt-2"
          onClick={() => setMediaIds((ids) => ids.filter((id) => !gone.includes(id)))}>
          <Trash2 size={12} /> {t("Buang gambar yang sudah dipadam", "Remove the deleted pictures")}</Button>}
        {post.errors?.scan && <p className="mt-2 text-[12px] text-danger">
          {t("Penerbit menyekat pada {at}", "The publisher blocked it at {at}", { at: stampMYT(post.errors.at) })}: {post.errors.scan.join(" · ")}</p>}
      </div>

      {post.status === "posted" && (
        <p className="rounded-tile bg-surface-2/60 p-2 text-[12px] text-muted">
          {post.archived_at
            ? t("Diarkibkan {at}: hanya kapsyen yang dihantar disimpan. Post ini tidak akan ditulis semula sebagai draf baharu.",
              "Archived {at}: only the captions that were sent are kept. This post will not be written again as a new draft.",
              { at: stampMYT(post.archived_at) })
            : t("Diterbitkan {at}. Ia diarkibkan secara automatik 24 jam selepas itu, dan tidak akan ditulis semula sebagai draf baharu.",
              "Published {at}. It is archived automatically 24 hours later, and will not be written again as a new draft.",
              { at: stampMYT(post.posted_at || post.updated_at) })}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {!locked && <Button variant="ghost" disabled={busy} onClick={() => write(content(), t("Disimpan.", "Saved."))}><Save size={13} /> {t("Simpan", "Save")}</Button>}
        {post.status !== "approved" && !locked && (
          <Button disabled={busy || blocking > 0 || !date || !slot} onClick={() => write({ ...content(), status: "approved", ...decided("approved") }, t("Diluluskan.", "Approved."))}
            title={blocking ? t("Selesaikan perkara bertanda ■ dahulu", "Resolve the items marked ■ first")
              : !date || !slot ? t("Pilih tarikh dan slot", "Choose a date and slot") : ""}>
            <Check size={13} /> {t("Luluskan", "Approve")}
          </Button>
        )}
        {post.status === "approved" && <Button variant="soft" disabled={busy} onClick={() => write({ status: "draft", ...decided("back to draft") }, t("Kembali ke draf.", "Back to draft."))}>
          <RotateCcw size={13} /> {t("Kembali ke draf", "Back to draft")}</Button>}
        {post.status === "rejected" && <Button variant="soft" disabled={busy} onClick={restore}>
          {t("Pulihkan", "Restore")}</Button>}
        {(post.status === "draft" || post.status === "rejected") && (
          <Button variant="danger" disabled={busy} onClick={async () => {
            const { error } = await supabase.from(TABLES.posts).delete().eq("id", post.id);
            if (error) onToast(errText(error), "danger"); else { onToast(t("Dipadam.", "Deleted."), "info"); onChanged(); onClose?.(); }
          }}><Trash2 size={13} /></Button>
        )}
      </div>

      <PostWorkflow post={post} dirty={dirty} locked={locked} mediaById={mediaById} lastLook={look} user={user}
        onToast={onToast} onChanged={onChanged} />

      {myLog.length > 0 && (
        <div>
          <Label>{t("Log penerbit", "Publisher log")}</Label>
          <ul className="space-y-1 text-[12px] text-muted">
            {myLog.map((l) => (
              <li key={l.id} className="flex gap-2">
                <Info size={12} className="mt-0.5 shrink-0" />
                <span>{stampMYT(l.at)} · <b>{l.channel}</b> · {({ dry_run: t("cubaan kering: akan dihantar", "dry run: would send"), sent: t("dihantar", "sent"),
                  error: t("ralat", "error"), blocked: t("disekat", "blocked") })[l.action] || l.action}
                  {l.detail?.why ? `: ${[].concat(l.detail.why).join("; ")}` : ""}
                  {l.detail?.would_send ? ` ${t("pada {at}, {c} aksara, {m} gambar", "at {at}, {c} characters, {m} pictures", {
                    at: stampMYT(l.detail.would_send.due_at), c: l.detail.chars, m: l.detail.would_send.media.length })}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ImagePlus, Info, RotateCcw, Save, Trash2, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { LIMITS, hardCount, normaliseSlides, platformsFor, scan, scanMedia } from "../lib/compliance";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";
import SlidesEditor, { fromRows, toRows } from "./SlidesEditor";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

const PLAT_LABEL = { instagram: "Instagram", facebook: "Facebook", threads: "Threads", linkedin: "LinkedIn" };

/* One post, the way Studio's drawer worked: the words per language and platform, the source,
   the position, the pictures, and the same checks the publisher will run — live, as you type.
   Approve is offered only when nothing blocks. Changing an approved post sends it back to
   draft (the database does that, not this page), so what was approved is what goes out. */
export default function PostEditor({ post, mediaById, mediaRows, log, brand, user, indoExtra, onToast, onChanged, onClose }) {
  const { t } = useLang();
  const [text, setText] = useState(post.text || {});
  const [lang, setLang] = useState(post.lang || (post.stream === "linkedin" ? "en" : "bm"));
  const [view, setView] = useState(post.lang || (post.stream === "linkedin" ? "en" : "bm"));
  const [citation, setCitation] = useState(post.citation || "");
  const [date, setDate] = useState(post.date || "");
  const [slot, setSlot] = useState(post.slot || "");
  const [mediaIds, setMediaIds] = useState(post.media_ids || []);
  const [slideRows, setSlideRows] = useState(toRows(post.slides));
  const [bg, setBg] = useState("none");
  const [busy, setBusy] = useState(false);
  const [newPic, setNewPic] = useState("");

  useEffect(() => {
    setText(post.text || {}); setLang(post.lang || "bm"); setView(post.lang || "bm"); setCitation(post.citation || "");
    setDate(post.date || ""); setSlot(post.slot || ""); setMediaIds(post.media_ids || []);
    setSlideRows(toRows(post.slides));
  }, [post]);

  const reg = brand.regulab;
  const plats = platformsFor(post.stream);
  const locked = post.status === "scheduled" || post.status === "posted";
  const chosen = mediaIds.map((id) => mediaById[id]).filter(Boolean);
  const candidates = mediaRows.filter((m) => m.status === "done" && m.generated_media_url && !mediaIds.includes(m.id)
    && m.mode !== "slides" && (m.post_id === post.id || (post.idea_id && m.idea_id === post.idea_id)));
  const pending = mediaRows.filter((m) => (m.post_id === post.id) && m.mode !== "slides"
    && (m.status === "pending" || m.status === "processing"));
  // `slides` exists once supabase/006_slides.sql has run; before that the editor says so and saves nothing new
  const hasSlides = post.slides !== undefined;
  const slides = normaliseSlides(fromRows(slideRows));
  const slideJobs = mediaRows.filter((m) => m.mode === "slides" && m.post_id === post.id)
    .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  const pictures = mediaRows.filter((m) => m.post_id === post.id && m.type === "image" && m.mode !== "slides" && m.status === "done");
  const bgOptions = [["none", t("Kertas", "Paper")], ["post_image", t("Gambar pertama post", "Post's first picture")],
    ...pictures.map((m, i) => [m.id, `${t("Gambar {n}", "Picture {n}", { n: i + 1 })}${m.prompt ? `: ${m.prompt.slice(0, 28)}` : ""}`])];

  const current = { ...post, text, lang, citation, date: date || null, slot: slot || null, media_ids: mediaIds,
    ...(hasSlides ? { slides } : {}),
    media: chosen.filter((m) => m.status === "done").map(scanMedia) };
  const flags = useMemo(() => scan(current, reg, reg.schedule, indoExtra), [JSON.stringify(current), reg, indoExtra]); // eslint-disable-line
  const hard = hardCount(flags);
  const shownFlags = !date || !slot
    ? [...flags, { hard: false, where: t("Kedudukan", "Position"), msg: "no date and slot yet: the publisher skips a post without one" }]
    : flags;

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

  async function renderSlides() {
    if (!slides.length) return onToast(t("Tulis sekurang-kurangnya satu slaid.", "Write at least one slide."), "warn");
    setBusy(true);
    const saved = await supabase.from(TABLES.posts).update(content()).eq("id", post.id).select().single();
    if (saved.error) { setBusy(false); return onToast(errText(saved.error), "danger"); }
    const { error } = await supabase.from(TABLES.media).insert({
      mode: "slides", type: "image", prompt: "", status: "pending", created_by: user.id,
      post_id: post.id, idea_id: post.idea_id,
      meta: { flow: "B", slides, stream: post.stream, citation, domain: post.domain, angle: post.angle, bg },
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
    const old = new Set(mediaRows.filter((m) => m.mode === "slides").map((m) => m.id));
    setMediaIds((ids) => {
      const at = Math.max(0, ids.findIndex((x) => old.has(x)));
      const kept = ids.filter((x) => !old.has(x));
      kept.splice(Math.min(at, kept.length), 0, id);
      return kept;
    });
    onToast(t("Set slaid dipilih. Tekan Simpan.", "Slide set chosen. Press Save."), "info");
  }

  async function queuePicture() {
    if (!newPic.trim()) return;
    const { error } = await supabase.from(TABLES.media).insert({
      mode: "prompt", type: "image", prompt: newPic.trim(), status: "pending", created_by: user.id,
      post_id: post.id, idea_id: post.idea_id, meta: { alt: "", flow: "B" },
    });
    if (error) return onToast(errText(error), "danger");
    setNewPic(""); onToast(t("Gambar baharu dalam giliran.", "New picture queued."), "ok"); onChanged();
  }

  const slots = (post.stream === "linkedin" ? brand.linkedin.slots : reg.slots) || [];
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
            <Label hint={`${v.length}${lim ? ` / ${lim.max}` : ""} ${t("aksara", "characters")}${
              view !== lang ? ` · ${t("tidak dihantar", "not sent")}` : ""}`}>{PLAT_LABEL[p]}</Label>
            <TextArea rows={p === "threads" ? 4 : 7} value={v} disabled={locked} onChange={(e) => setCaption(view, p, e.target.value)}
              className={lim && v.length > lim.max ? "border-danger" : ""} />
          </label>
        );
      })}

      <label className="block"><Label hint={t("instrumen / pengawal selia, bukan portal berita", "instrument / regulator, not a news portal")}>
        {t("Sumber", "Source")}</Label>
        <Input value={citation} disabled={locked} onChange={(e) => setCitation(e.target.value)} /></label>

      <div className="flex flex-wrap items-end gap-3">
        <label><Label>{t("Tarikh (MYT)", "Date (MYT)")}</Label><Input type="date" value={date || ""} disabled={locked} onChange={(e) => setDate(e.target.value)} className="w-44" /></label>
        <label><Label>Slot</Label><Select value={slot || ""} disabled={locked} onChange={setSlot} options={[["", "—"], ...slots.map((s) => [s, s])]} /></label>
      </div>

      <div>
        <Label hint={t("urutan = urutan dihantar", "order = order sent")}>{t("Gambar", "Pictures")}</Label>
        <div className="flex flex-wrap gap-2">
          {chosen.map((m) => (
            <span key={m.id} className="relative">
              {m.mode === "slides" && <span className="absolute bottom-1 left-1 z-10 rounded bg-ink/80 px-1 text-[10px] text-bg">{t("{n} slaid", ["{n} slide", "{n} slides"], { n: m.meta?.count || "?" })}</span>}
              {m.type === "video"
                ? <video src={m.generated_media_url} className="h-24 w-24 rounded-tile bg-black object-cover" muted />
                : <img src={m.generated_media_url || m.reference_url} alt={m.meta?.alt || ""} className="h-24 w-24 rounded-tile object-cover" />}
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
                  ? <video src={m.generated_media_url} className="h-14 w-14 rounded-tile bg-black object-cover opacity-80 hover:opacity-100" muted />
                  : <img src={m.generated_media_url} alt="" className="h-14 w-14 rounded-tile object-cover opacity-80 hover:opacity-100" />}
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
            <Button type="button" size="sm" variant="soft" onClick={queuePicture} disabled={!newPic.trim()}><ImagePlus size={12} /> {t("Jana", "Generate")}</Button>
          </div>
        )}
      </div>

      {hasSlides ? (
        <SlidesEditor post={post} rows={slideRows} setRows={setSlideRows} locked={locked} jobs={slideJobs}
          attachedIds={mediaIds} bg={bg} setBg={setBg} bgOptions={bgOptions} busy={busy}
          onRender={renderSlides} onUse={chooseSet} />
      ) : (
        <p className="rounded-tile border border-dashed border-line p-3 text-[12px] text-muted">
          {t("Slaid carousel belum tersedia: jalankan", "Carousel slides are not available yet: run")} <code>supabase/006_slides.sql</code>{" "}
          {t("sekali di Supabase SQL editor.", "once in the Supabase SQL editor.")}
        </p>
      )}

      <div className="rounded-tile border border-line p-3">
        <p className={`flex items-center gap-1.5 text-sm font-medium ${hard ? "text-danger" : "text-ok"}`}>
          {hard ? <AlertTriangle size={14} /> : <Check size={14} />}
          {hard ? t("{n} perkara menyekat kelulusan", ["{n} item blocking approval", "{n} items blocking approval"], { n: hard }) : t("Semakan lulus", "Checks passed")}
        </p>
        <ul className="mt-2 space-y-1 text-[12px]">
          {shownFlags.map((f, i) => (
            <li key={i} className={f.hard ? "text-danger" : "text-muted"}>
              {f.hard ? "■" : "□"} <b>{f.where}</b>: {f.msg}
            </li>
          ))}
        </ul>
        {post.errors?.scan && <p className="mt-2 text-[12px] text-danger">
          {t("Penerbit menyekat pada {at}", "The publisher blocked it at {at}", { at: stampMYT(post.errors.at) })}: {post.errors.scan.join(" · ")}</p>}
      </div>

      <div className="flex flex-wrap gap-2">
        {!locked && <Button variant="ghost" disabled={busy} onClick={() => write(content(), t("Disimpan.", "Saved."))}><Save size={13} /> {t("Simpan", "Save")}</Button>}
        {post.status !== "approved" && !locked && (
          <Button disabled={busy || hard > 0 || !date || !slot} onClick={() => write({ ...content(), status: "approved" }, t("Diluluskan.", "Approved."))}
            title={hard ? t("Selesaikan perkara bertanda ■ dahulu", "Resolve the items marked ■ first")
              : !date || !slot ? t("Pilih tarikh dan slot", "Choose a date and slot") : ""}>
            <Check size={13} /> {t("Luluskan", "Approve")}
          </Button>
        )}
        {post.status === "approved" && <Button variant="soft" disabled={busy} onClick={() => write({ status: "draft" }, t("Kembali ke draf.", "Back to draft."))}>
          <RotateCcw size={13} /> {t("Kembali ke draf", "Back to draft")}</Button>}
        {(post.status === "draft" || post.status === "approved") && <Button variant="ghost" disabled={busy} onClick={() => write({ status: "rejected" }, t("Ditolak.", "Rejected."))}>
          {t("Tolak", "Reject")}</Button>}
        {post.status === "rejected" && <Button variant="soft" disabled={busy} onClick={() => write({ status: "draft" }, t("Dipulihkan ke draf.", "Restored to draft."))}>
          {t("Pulihkan", "Restore")}</Button>}
        {(post.status === "draft" || post.status === "rejected") && (
          <Button variant="danger" disabled={busy} onClick={async () => {
            const { error } = await supabase.from(TABLES.posts).delete().eq("id", post.id);
            if (error) onToast(errText(error), "danger"); else { onToast(t("Dipadam.", "Deleted."), "info"); onChanged(); onClose?.(); }
          }}><Trash2 size={13} /></Button>
        )}
      </div>

      {myLog.length > 0 && (
        <div>
          <Label>{t("Log penerbit", "Publisher log")}</Label>
          <ul className="space-y-1 text-[12px] text-muted">
            {myLog.map((l) => (
              <li key={l.id} className="flex gap-2">
                <Info size={12} className="mt-0.5 shrink-0" />
                <span>{stampMYT(l.at)} · <b>{l.channel}</b> · {l.action === "dry_run" ? t("cubaan kering: akan dihantar", "dry run: would send") : l.action}
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

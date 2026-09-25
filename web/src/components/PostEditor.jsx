import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, ImagePlus, Info, RotateCcw, Save, Trash2, X } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { LIMITS, hardCount, platformsFor, scan } from "../lib/compliance";
import { stampMYT } from "../lib/format";
import Button from "./ui/Button";
import { Input, Label, Segmented, Select, TextArea } from "./ui/Field";

const PLAT_LABEL = { instagram: "Instagram", facebook: "Facebook", threads: "Threads", linkedin: "LinkedIn" };

/* One post, the way Studio's drawer worked: the words per language and platform, the source,
   the position, the pictures, and the same checks the publisher will run — live, as you type.
   Approve is offered only when nothing blocks. Changing an approved post sends it back to
   draft (the database does that, not this page), so what was approved is what goes out. */
export default function PostEditor({ post, mediaById, mediaRows, log, brand, user, onToast, onChanged, onClose }) {
  const [text, setText] = useState(post.text || {});
  const [lang, setLang] = useState(post.lang || (post.stream === "linkedin" ? "en" : "bm"));
  const [view, setView] = useState(post.lang || (post.stream === "linkedin" ? "en" : "bm"));
  const [citation, setCitation] = useState(post.citation || "");
  const [date, setDate] = useState(post.date || "");
  const [slot, setSlot] = useState(post.slot || "");
  const [mediaIds, setMediaIds] = useState(post.media_ids || []);
  const [busy, setBusy] = useState(false);
  const [newPic, setNewPic] = useState("");

  useEffect(() => {
    setText(post.text || {}); setLang(post.lang || "bm"); setView(post.lang || "bm"); setCitation(post.citation || "");
    setDate(post.date || ""); setSlot(post.slot || ""); setMediaIds(post.media_ids || []);
  }, [post]);

  const reg = brand.regulab;
  const plats = platformsFor(post.stream);
  const locked = post.status === "scheduled" || post.status === "posted";
  const chosen = mediaIds.map((id) => mediaById[id]).filter(Boolean);
  const candidates = mediaRows.filter((m) => m.status === "done" && m.generated_media_url && !mediaIds.includes(m.id)
    && (m.post_id === post.id || (post.idea_id && m.idea_id === post.idea_id)));
  const pending = mediaRows.filter((m) => (m.post_id === post.id) && (m.status === "pending" || m.status === "processing"));

  const current = { ...post, text, lang, citation, date: date || null, slot: slot || null, media_ids: mediaIds,
    media: chosen.filter((m) => m.status === "done").map((m) => ({ alt: m.meta?.alt || "" })) };
  const flags = useMemo(() => scan(current, reg, reg.schedule), [JSON.stringify(current), reg]); // eslint-disable-line
  const hard = hardCount(flags);
  const shownFlags = !date || !slot
    ? [...flags, { hard: false, where: "Kedudukan", msg: "no date and slot yet: the publisher skips a post without one" }]
    : flags;

  function setCaption(lg, plat, v) {
    setText((t) => ({ ...t, [lg]: { ...(t[lg] || {}), [plat]: v } }));
  }

  async function write(patch, msg) {
    setBusy(true);
    const { data, error } = await supabase.from(TABLES.posts).update(patch).eq("id", post.id).select().single();
    setBusy(false);
    if (error) return onToast(errText(error), "danger");
    if (post.status === "approved" && patch.status === undefined && data.status === "draft") {
      onToast("Disimpan. Post ini diubah selepas diluluskan, jadi ia kembali ke draf: luluskan semula.", "warn");
    } else onToast(msg, "ok");
    onChanged();
  }

  const content = () => ({ text, lang, citation, date: date || null, slot: slot || null, media_ids: mediaIds,
    flags, hard_flags: hard });

  async function queuePicture() {
    if (!newPic.trim()) return;
    const { error } = await supabase.from(TABLES.media).insert({
      mode: "prompt", type: "image", prompt: newPic.trim(), status: "pending", created_by: user.id,
      post_id: post.id, idea_id: post.idea_id, meta: { alt: "", flow: "B" },
    });
    if (error) return onToast(errText(error), "danger");
    setNewPic(""); onToast("Gambar baharu dalam giliran.", "ok"); onChanged();
  }

  const slots = (post.stream === "linkedin" ? brand.linkedin.slots : reg.slots) || [];
  const myLog = log.filter((l) => l.post_id === post.id).slice(0, 12);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented value={view} onChange={setView} options={[["bm", "BM"], ["en", "EN"]]} />
        <span className="text-xs text-muted">Bahasa yang dihantar:</span>
        <Select value={lang} onChange={setLang} options={[["bm", "BM"], ["en", "EN"]]} disabled={locked} aria-label="Bahasa dihantar" />
        {onClose && <button type="button" onClick={onClose} className="ml-auto text-sm text-muted hover:text-ink" aria-label="Tutup"><X size={16} /></button>}
      </div>

      {plats.map((p) => {
        const v = ((text[view] || {})[p]) || "";
        const lim = (LIMITS[post.stream] || {})[p];
        return (
          <label key={p} className="block">
            <Label hint={`${v.length}${lim ? ` / ${lim.max}` : ""} aksara${view !== lang ? " · tidak dihantar" : ""}`}>{PLAT_LABEL[p]}</Label>
            <TextArea rows={p === "threads" ? 4 : 7} value={v} disabled={locked} onChange={(e) => setCaption(view, p, e.target.value)}
              className={lim && v.length > lim.max ? "border-danger" : ""} />
          </label>
        );
      })}

      <label className="block"><Label hint="instrumen / pengawal selia, bukan portal berita">Sumber</Label>
        <Input value={citation} disabled={locked} onChange={(e) => setCitation(e.target.value)} /></label>

      <div className="flex flex-wrap items-end gap-3">
        <label><Label>Tarikh (MYT)</Label><Input type="date" value={date || ""} disabled={locked} onChange={(e) => setDate(e.target.value)} className="w-44" /></label>
        <label><Label>Slot</Label><Select value={slot || ""} disabled={locked} onChange={setSlot} options={[["", "—"], ...slots.map((s) => [s, s])]} /></label>
      </div>

      <div>
        <Label hint="urutan = urutan dihantar">Gambar</Label>
        <div className="flex flex-wrap gap-2">
          {chosen.map((m) => (
            <span key={m.id} className="relative">
              {m.type === "video"
                ? <video src={m.generated_media_url} className="h-24 w-24 rounded-tile bg-black object-cover" muted />
                : <img src={m.generated_media_url || m.reference_url} alt={m.meta?.alt || ""} className="h-24 w-24 rounded-tile object-cover" />}
              {!locked && <button type="button" aria-label="Buang gambar" onClick={() => setMediaIds((ids) => ids.filter((x) => x !== m.id))}
                className="absolute -right-1 -top-1 rounded-full bg-ink p-0.5 text-bg"><X size={11} /></button>}
            </span>
          ))}
          {!chosen.length && <span className="text-xs text-muted">Belum ada gambar dipilih.</span>}
        </div>
        {!locked && candidates.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-muted">Tambah:</span>
            {candidates.map((m) => (
              <button type="button" key={m.id} onClick={() => setMediaIds((ids) => [...ids, m.id])} title={m.prompt}>
                {m.type === "video"
                  ? <video src={m.generated_media_url} className="h-14 w-14 rounded-tile bg-black object-cover opacity-80 hover:opacity-100" muted />
                  : <img src={m.generated_media_url} alt="" className="h-14 w-14 rounded-tile object-cover opacity-80 hover:opacity-100" />}
              </button>
            ))}
          </div>
        )}
        {pending.length > 0 && <p className="mt-1 text-[11px] text-muted">{pending.length} gambar sedang dijana; ia masuk ke sini sendiri selagi post ini draf.</p>}
        {!locked && (
          <div className="mt-2 flex gap-2">
            <Input value={newPic} onChange={(e) => setNewPic(e.target.value)} placeholder="Jana gambar lain: terangkan gambarnya…" />
            <Button type="button" size="sm" variant="soft" onClick={queuePicture} disabled={!newPic.trim()}><ImagePlus size={12} /> Jana</Button>
          </div>
        )}
      </div>

      <div className="rounded-tile border border-line p-3">
        <p className={`flex items-center gap-1.5 text-sm font-medium ${hard ? "text-danger" : "text-ok"}`}>
          {hard ? <AlertTriangle size={14} /> : <Check size={14} />}
          {hard ? `${hard} perkara menyekat kelulusan` : "Semakan lulus"}
        </p>
        <ul className="mt-2 space-y-1 text-[12px]">
          {shownFlags.map((f, i) => (
            <li key={i} className={f.hard ? "text-danger" : "text-muted"}>
              {f.hard ? "■" : "□"} <b>{f.where}</b>: {f.msg}
            </li>
          ))}
        </ul>
        {post.errors?.scan && <p className="mt-2 text-[12px] text-danger">Penerbit menyekat pada {stampMYT(post.errors.at)}: {post.errors.scan.join(" · ")}</p>}
      </div>

      <div className="flex flex-wrap gap-2">
        {!locked && <Button variant="ghost" disabled={busy} onClick={() => write(content(), "Disimpan.")}><Save size={13} /> Simpan</Button>}
        {post.status !== "approved" && !locked && (
          <Button disabled={busy || hard > 0 || !date || !slot} onClick={() => write({ ...content(), status: "approved" }, "Diluluskan.")}
            title={hard ? "Selesaikan perkara bertanda ■ dahulu" : !date || !slot ? "Pilih tarikh dan slot" : ""}>
            <Check size={13} /> Luluskan
          </Button>
        )}
        {post.status === "approved" && <Button variant="soft" disabled={busy} onClick={() => write({ status: "draft" }, "Kembali ke draf.")}><RotateCcw size={13} /> Kembali ke draf</Button>}
        {(post.status === "draft" || post.status === "approved") && <Button variant="ghost" disabled={busy} onClick={() => write({ status: "rejected" }, "Ditolak.")}>Tolak</Button>}
        {post.status === "rejected" && <Button variant="soft" disabled={busy} onClick={() => write({ status: "draft" }, "Dipulihkan ke draf.")}>Pulihkan</Button>}
        {(post.status === "draft" || post.status === "rejected") && (
          <Button variant="danger" disabled={busy} onClick={async () => {
            const { error } = await supabase.from(TABLES.posts).delete().eq("id", post.id);
            if (error) onToast(errText(error), "danger"); else { onToast("Dipadam.", "info"); onChanged(); onClose?.(); }
          }}><Trash2 size={13} /></Button>
        )}
      </div>

      {myLog.length > 0 && (
        <div>
          <Label>Log penerbit</Label>
          <ul className="space-y-1 text-[12px] text-muted">
            {myLog.map((l) => (
              <li key={l.id} className="flex gap-2">
                <Info size={12} className="mt-0.5 shrink-0" />
                <span>{stampMYT(l.at)} · <b>{l.channel}</b> · {l.action === "dry_run" ? "cubaan kering: akan dihantar" : l.action}
                  {l.detail?.why ? `: ${[].concat(l.detail.why).join("; ")}` : ""}
                  {l.detail?.would_send ? ` pada ${stampMYT(l.detail.would_send.due_at)}, ${l.detail.chars} aksara, ${l.detail.would_send.media.length} gambar` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

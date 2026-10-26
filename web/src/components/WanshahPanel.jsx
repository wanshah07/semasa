import { useMemo, useState } from "react";
import { Bot, Check, ImagePlus, Loader2, Plus, RotateCcw } from "lucide-react";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { Label, TextArea } from "./ui/Field";
import { useLang } from "../lib/i18n";
import { MASCOTS } from "../lib/cards/library";
import { uploadReference } from "../lib/storage";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { DEFAULT_LOOK, POSES, buildPrompt, floodTransparent, opaqueBox } from "../lib/wanshah";

/* Design → Wanshah: make the 3D robot's four poses with the image provider set in Tetapan → AI, approve each one, and the card
   renderer draws it in place of the old pose (library.js setWanshah). Nothing is replaced until you press Guna. */
export default function WanshahPanel({ user, gens, settings, saveSetting, onToast }) {
  const { t, lang } = useLang();
  const row = settings?.wanshah || {};
  const poses = row.poses && typeof row.poses === "object" ? row.poses : {};
  const [look, setLook] = useState(String(row.look || ""));
  const [busy, setBusy] = useState("");
  const mine = useMemo(() => (gens?.rows || []).filter((g) => g.meta?.wanshah), [gens]);
  const byPose = (k) => mine.filter((g) => g.meta.wanshah === k).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at))).slice(0, 4);

  async function generate(only) {
    setBusy("gen");
    try {
      const keep = look.trim();
      if (keep !== String(row.look || "")) await saveSetting("wanshah", { ...row, look: keep });
      const list = only ? POSES.filter((p) => p.k === only) : POSES;
      const rows = list.map((p) => ({
        mode: "prompt", type: "image", provider: null, status: "pending", created_by: user.id,
        prompt: buildPrompt(p.k, keep), meta: { wanshah: p.k, look: keep || DEFAULT_LOOK },
      }));
      const { error } = await supabase.from(TABLES.media).insert(rows);
      if (error) throw new Error(errText(error));
      gens?.reload?.();
      onToast(t("{n} gambar Wanshah dihantar. Ia muncul di sini dalam satu dua minit; pilih yang terbaik dan tekan Guna.",
        "{n} Wanshah pictures sent. They appear here in a minute or two; pick the best and press Use.", { n: rows.length }), "ok");
    } catch (e) { onToast(e.message, "danger"); }
    setBusy("");
  }

  async function use(pose, gen) {
    setBusy(gen.id);
    try {
      const img = await new Promise((ok, no) => { const i = new Image(); i.crossOrigin = "anonymous"; i.onload = () => ok(i); i.onerror = () => no(new Error(t("Gambar tidak dapat dimuatkan.", "The picture could not be loaded."))); i.src = gen.generated_media_url; });
      const scale = Math.min(1, 900 / Math.max(img.naturalWidth, img.naturalHeight));
      const w = Math.round(img.naturalWidth * scale), h = Math.round(img.naturalHeight * scale);
      const c = document.createElement("canvas"); c.width = w; c.height = h;
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(img, 0, 0, w, h);
      const data = ctx.getImageData(0, 0, w, h);
      const cleared = floodTransparent(data.data, w, h);
      if (cleared < 0) throw new Error(t("Latar gambar ini tidak rata putih, jadi tidak dapat dipotong bersih. Jana semula.", "This picture's background is not flat white, so it cannot be cut out cleanly. Generate it again."));
      ctx.putImageData(data, 0, 0);
      const box = opaqueBox(data.data, w, h);
      if (!box) throw new Error(t("Tiada apa tinggal selepas potongan. Jana semula.", "Nothing is left after the cut-out. Generate it again."));
      const out = document.createElement("canvas"); out.width = box.w; out.height = box.h;
      out.getContext("2d").drawImage(c, box.x, box.y, box.w, box.h, 0, 0, box.w, box.h);
      const blob = await new Promise((ok) => out.toBlob(ok, "image/png"));
      const up = await uploadReference(user, new File([blob], `wanshah-${pose}.png`, { type: "image/png" }));
      await saveSetting("wanshah", { ...row, look: look.trim(), poses: { ...poses, [pose]: { url: up.url, path: up.path, from: gen.id } } });
      onToast(t("Wanshah dipakai untuk pose ini. Kad yang dilukis lepas ini guna dia.", "Wanshah now stands in for this pose. Cards drawn from now on use him."), "ok");
    } catch (e) { onToast(e.message, "danger"); }
    setBusy("");
  }

  async function reset(pose) {
    setBusy("reset-" + pose);
    try {
      const next = { ...poses }; delete next[pose];
      await saveSetting("wanshah", { ...row, poses: next });
      onToast(t("Pose asal dipulihkan.", "The original pose is back."), "ok");
    } catch (e) { onToast(e.message, "danger"); }
    setBusy("");
  }

  const L = lang === "bm" ? "bm" : "en";
  return (
    <Card className="mt-2 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 font-display text-xl"><Bot size={18} className="text-accent" /> Wanshah</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            {t("Maskot robot 3D untuk semua kad. Semasa lukis empat pose guna penjana imej di Tetapan → AI; anda pilih dan tekan Guna, dan pose lama diganti. Tekan Asal untuk kembalikan.",
              "The 3D robot mascot for every card. Semasa draws four poses with the image provider in Settings → AI; you pick and press Use, and the old pose is replaced. Press Original to put it back.")}
          </p>
        </div>
        <Button onClick={() => generate()} disabled={busy === "gen"}>{busy === "gen" ? <Loader2 size={14} className="animate-spin" /> : <ImagePlus size={14} />} {t("Jana Wanshah", "Generate Wanshah")}</Button>
      </div>
      <label className="mt-4 block"><Label>{t("Rupa (satu atau dua ayat; kosong = rupa biasa)", "Look (a sentence or two; empty = the default look)")}</Label>
        <TextArea rows={2} value={look} onChange={(e) => setLook(e.target.value)} placeholder={DEFAULT_LOOK} /></label>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4 [&>*]:min-w-0">
        {POSES.map((p) => {
          const m = MASCOTS.find((x) => x.k === p.k);
          const done = byPose(p.k).filter((g) => g.status === "done" && g.generated_media_url);
          const waiting = byPose(p.k).some((g) => g.status === "pending" || g.status === "working");
          const failed = byPose(p.k).find((g) => g.status === "error");
          return (
            <div key={p.k} className="rounded-tile border border-line p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium">{p[L]}</p>
                {poses[p.k] ? <span className="rounded-pill bg-ok/10 px-2 py-0.5 text-[10px] text-ok">Wanshah</span> : <span className="rounded-pill bg-surface-2 px-2 py-0.5 text-[10px] text-muted">{t("asal", "original")}</span>}
              </div>
              <div className="mt-2 grid h-36 place-items-center rounded-tile bg-surface-2/60">
                {m && <img src={m.url} alt={p[L]} className="max-h-32 max-w-full object-contain" />}
              </div>
              {waiting && <p className="mt-2 flex items-center gap-1 text-[11px] text-muted"><Loader2 size={11} className="animate-spin" /> {t("sedang dilukis…", "drawing…")}</p>}
              {failed && !waiting && !done.length && <p className="mt-2 [overflow-wrap:anywhere] text-[11px] text-danger">{String(failed.error || "").slice(0, 160)}</p>}
              {done.length > 0 && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  {done.map((g) => (
                    <div key={g.id} className="min-w-0">
                      <img src={g.generated_media_url} alt="" loading="lazy" className="aspect-square w-full rounded-tile border border-line bg-white object-contain" />
                      <Button size="sm" variant="ghost" className="mt-1 w-full" disabled={!!busy} onClick={() => use(p.k, g)}>
                        {busy === g.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} {t("Guna", "Use")}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-1">
                <Button size="sm" variant="ghost" disabled={busy === "gen"} onClick={() => generate(p.k)}><Plus size={12} /> {t("Lagi", "More")}</Button>
                {poses[p.k] && <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => reset(p.k)}><RotateCcw size={12} /> {t("Asal", "Original")}</Button>}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

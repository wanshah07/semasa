/* The storyboard a film waits on (Wan, 7 Nov 2026: "make sure all storyboard appear and approve before proceed for motion
   creation"). The worker saves it on the row (`storyboard`, supabase/071) and sets the film to 'review'; nothing is drawn or
   rendered until Wan approves it, here or on Telegram. This file turns the saved storyboard into editable scenes and puts the
   edits back in the same shape the worker reads (backend/semasa/motion_review.py), which checks every word again. */

export const isReview = (row) => row?.status === "review";
export const hasStoryboardColumns = (row) => !!row && Object.prototype.hasOwnProperty.call(row, "storyboard");

const str = (v) => (v == null ? "" : String(v));
const list = (v) => (Array.isArray(v) ? v.map(str) : []);
const clone = (v) => JSON.parse(JSON.stringify(v ?? null));

/** Each scene as { key, label, heading, lines, said, shot, edit: {heading, lines, said, shot} } where `edit` says which of the
 *  four can be changed (false = shown, not editable). */
/** What the subject IS (Wan, 10 Nov 2026: "setiap kali storyboard explain apa yang patut"): [{term, meaning}] of an explainer. */
export function termsOf(sb) {
  const t = sb?.kind === "explainer" ? sb?.plan?.terms : sb?.sb?.terms;   // the explainer's plan, or a template's storyboard
  return Array.isArray(t) ? t.filter((x) => x && str(x.term)).map((x) => ({ term: str(x.term), meaning: str(x.meaning) })) : [];
}

/** The preview sheet of the film (one frame a scene), or null: only an https address is ever shown. */
export function previewOf(sb) {
  const p = sb?.kind === "explainer" ? sb?.plan?.preview : null;
  const sheet = str(p?.sheet);
  return sheet.startsWith("https://") ? { sheet, frames: list(p?.frames).filter((u) => u.startsWith("https://")), engine: str(p?.engine) } : null;
}

export function scenesOf(sb) {
  if (!sb || typeof sb !== "object") return [];
  if (sb.kind === "explainer") {
    return (sb.plan?.scenes || []).map((sc, i) => {
      const outro = sc?.id === "brand-outro";
      // the label is the scene's number: the writer's own labels (HOOK, FAKTA...) are not shown (Wan, 10 Nov 2026)
      return { key: `e${i}`, label: outro ? "Penutup" : `Babak ${i + 1}`, image: str(sc?.image), heading: str(sc?.heading), lines: list(sc?.lines),
        said: str(sc?.narration), shot: str(sc?.shot), hookShape: i === 0 ? sc?.hook_shape ?? null : null,
        edit: outro ? { heading: false, lines: false, said: false, shot: false } : { heading: true, lines: true, said: true, shot: !!sc?.shot } };
    });
  }
  const b = sb.sb || {};
  if (sb.kind === "comic") {
    // the daily comic series (backend/semasa/comic_daily.py): the title with the source the system built, then the four panels with the
    // people's words (one line a bubble, "Name: words") and the scene the artist is given. The source line is shown, never editable.
    const names = b.names || {};
    return [{ key: "title", label: "Tajuk", heading: str(b.title), lines: [`Siri ${str(b.series_name)} · Episod ${str(b.episode)}`, `Sumber: ${str(b.source)}`],
      said: "", shot: "", hookShape: null, edit: { heading: true, lines: false, said: false, shot: false } },
    ...(b.panels || []).map((p, i) => ({ key: `c${i}`, label: `Panel ${i + 1}`, heading: "",
      lines: (p?.lines || []).map((l) => `${str(names[l?.who] || l?.who)}: ${str(l?.text)}`), said: "", shot: str(p?.scene), hookShape: null,
      edit: { heading: false, lines: true, said: false, shot: true } }))];
  }
  if (sb.kind === "story") {
    return [...(b.scenes || []).map((sc, i) => ({ key: `s${i}`, label: String(i + 1).padStart(2, "0"),
      heading: i === 0 ? str(b.hook) : str(sc?.caption), lines: [], said: "", shot: str(sc?.prompt), hookShape: i === 0 ? b.hook_shape ?? null : null,
      edit: { heading: true, lines: false, said: false, shot: true } })),
    { key: "end", label: "Penutup", heading: str(b.title), lines: [str(b.subtitle)], said: "", shot: "", hookShape: null,
      edit: { heading: true, lines: true, said: false, shot: false } }];
  }
  if (sb.kind === "showcase") {
    const head = Array.isArray(b.headline) ? b.headline : ["", ""];
    return [{ key: "intro", label: "Intro", heading: str(b.hook), lines: [str(b.title)], said: "", shot: str(b.background), hookShape: b.hook_shape ?? null,
      edit: { heading: true, lines: true, said: false, shot: true } },
    ...(b.products || []).map((p, i) => ({ key: `p${i}`, label: `Produk ${i + 1}`, heading: str(p?.name), lines: list(p?.benefits), said: "", shot: "",
      hookShape: null, edit: { heading: true, lines: true, said: false, shot: false } })),
    { key: "finale", label: "Penutup", heading: str(b.caption), lines: head.map(str), said: "", shot: "", hookShape: null,
      edit: { heading: true, lines: true, said: false, shot: false } }];
  }
  return [];
}

/** The bubbles of a panel from the lines Wan edited ("Name: words" one a line): a name that is one of the two people's sets who speaks,
    a line with no name keeps the speaker the bubble had (else the other person), an empty line is no bubble. The worker checks the
    result again (a panel has one or two bubbles, each person once, every rule a comic has). */
export function comicLines(lines, before, names) {
  const byName = Object.fromEntries(Object.entries(names || {}).map(([who, name]) => [String(name).toLowerCase(), who]));
  return (lines || []).map((raw, k) => {
    const m = String(raw).match(/^\s*([^:]{1,40}?)\s*:\s*(.*)$/s);
    const who = m && byName[m[1].toLowerCase()];
    const text = (who ? m[2] : String(raw)).replace(/\s+/g, " ").trim();
    return { who: who || before[k]?.who || (k === 0 ? "A" : "B"), text };
  }).filter((l) => l.text);
}

const linesOf = (text) => str(text).split("\n").map((x) => x.trim()).filter(Boolean);

/** The saved storyboard with the edits put back: `edits` is { [scene key]: { heading?, lines? (text, one a line), said?, shot? } }.
 *  Only the fields scenesOf marks editable are taken; everything else is kept exactly as the worker saved it. */
export function withEdits(sb, edits = {}) {
  const out = clone(sb);
  if (!out || typeof out !== "object") return out;
  const scenes = scenesOf(sb);
  const pick = (key, field) => {
    const sc = scenes.find((x) => x.key === key);
    const e = edits?.[key];
    if (!sc || !e || !sc.edit[field] || e[field] === undefined) return undefined;
    return field === "lines" ? linesOf(e[field]) : str(e[field]).trim();
  };
  if (out.kind === "explainer") {
    (out.plan?.scenes || []).forEach((sc, i) => {
      const k = `e${i}`;
      const h = pick(k, "heading"); if (h !== undefined) sc.heading = h;
      const l = pick(k, "lines"); if (l !== undefined) sc.lines = l;
      const s = pick(k, "said"); if (s !== undefined) sc.narration = s;
      const p = pick(k, "shot"); if (p !== undefined) sc.shot = p;
    });
    // the hook is scene 1's heading; a teaser's heading also carries " · <call to action>", which is the film's own (the worker
    // puts it back), so it is not part of the hook
    if (out.plan?.scenes?.[0] && pick("e0", "heading") !== undefined) out.plan.hook = str(out.plan.scenes[0].heading).split(" · ")[0];
    return out;
  }
  const b = out.sb || {};
  if (out.kind === "comic") {
    const t = pick("title", "heading"); if (t !== undefined) b.title = t;
    (b.panels || []).forEach((p, i) => {
      const l = pick(`c${i}`, "lines");
      if (l !== undefined) p.lines = comicLines(l, p.lines || [], b.names || {});
      const sh = pick(`c${i}`, "shot"); if (sh !== undefined) p.scene = sh;
    });
    return out;
  }
  if (out.kind === "story") {
    (b.scenes || []).forEach((sc, i) => {
      const h = pick(`s${i}`, "heading");
      if (h !== undefined) { if (i === 0) b.hook = h; sc.caption = h; }
      const p = pick(`s${i}`, "shot"); if (p !== undefined) sc.prompt = p;
    });
    const t = pick("end", "heading"); if (t !== undefined) b.title = t;
    const sub = pick("end", "lines"); if (sub !== undefined) b.subtitle = sub.join(" ");
    return out;
  }
  if (out.kind === "showcase") {
    const h = pick("intro", "heading"); if (h !== undefined) b.hook = h;
    const t = pick("intro", "lines"); if (t !== undefined) b.title = t.join(" ");
    const bg = pick("intro", "shot"); if (bg !== undefined) b.background = bg;
    (b.products || []).forEach((p, i) => {
      const n = pick(`p${i}`, "heading"); if (n !== undefined) p.name = n;
      const l = pick(`p${i}`, "lines"); if (l !== undefined) p.benefits = l;
    });
    const c = pick("finale", "heading"); if (c !== undefined) b.caption = c;
    const hl = pick("finale", "lines"); if (hl !== undefined) b.headline = hl;
    return out;
  }
  return out;
}

/** The storyboard's written_at in whole seconds, sent with every decision so it only ever applies to the storyboard shown
 *  (supabase/071 answers 'changed' when the worker has written a newer one since). */
export function writtenEpoch(sb) {
  const t = Date.parse(sb?.written_at || "");
  return Number.isFinite(t) ? Math.floor(t / 1000) : null;
}

/** True when any edit differs from what was saved. */
export function changed(sb, edits = {}) {
  return JSON.stringify(withEdits(sb, edits)) !== JSON.stringify(sb);
}

/** The fields "Make again" writes: a new storyboard, so a new approval (071 columns only when the row has them). */
export function remakeFields(row) {
  return { status: "pending", attempts: 0, error: "",
    ...(hasStoryboardColumns(row) ? { storyboard: null, storyboard_approved_at: null, storyboard_approved_by: null, stage: "" } : {}) };
}

/** A failed film whose storyboard was approved can carry on from it, without asking for a new one. */
export const canContinue = (row) => row?.status === "error" && !!row?.storyboard_approved_at && !!row?.storyboard;
export const continueFields = () => ({ status: "pending", attempts: 0, error: "" });

export const DECIDE_WORDS = {
  ok: ["Diluluskan: Semasa mula buat gambar dan video.", "Approved: Semasa starts the pictures and the film."],
  rewrite: ["Storyboard baharu sedang ditulis.", "A new storyboard is being written."],
  gone: ["Video itu sudah tiada.", "That film is gone."],
  no_storyboard: ["Tiada storyboard untuk diluluskan.", "There is no storyboard to approve."],
  bad_storyboard: ["Storyboard itu rosak: tekan Tulis semula.", "That storyboard is broken: press Write again."],
  changed: ["Storyboard sudah diganti dengan yang baharu: semak versi terkini dahulu.", "The storyboard was replaced by a newer one: read the latest first."],
};
export function decideWords(res, action, L = 0) {
  if (res === "ok") return DECIDE_WORDS[action === "approve" ? "ok" : "rewrite"][L];
  if (String(res).startsWith("status:")) return L ? `It is no longer waiting for approval (${res.slice(7)}).` : `Ia tidak lagi menunggu kelulusan (${res.slice(7)}).`;
  return (DECIDE_WORDS[res] || [String(res), String(res)])[L];
}

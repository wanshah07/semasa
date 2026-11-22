// Every caption inside its platform's limit (Wan, 22 Nov 2026: "Make sure caption untuk semua platform di bawah maksimum aksara
// dibenarkan"). The same rule as backend/semasa/caption_fit.py: the hashtags and the follow line at the end stay, whole paragraphs
// come out of the END of the body (the hook is the last to go), and only one paragraph that is itself over the limit is cut, at
// its last full sentence. A Threads caption becomes a chain of at most 5 posts of 500, separated by a line holding only ---, with
// the hashtags on the last post. Lengths are UTF-16 units (a JS string's length), which is what the platforms count.
import { LIMITS, threadParts } from "./compliance.js";

const TIKTOK_MAX = 2200;
const SEP = "---";
const TAGS_ONLY = /^(?:\s*#[^\s#]+)+\s*$/;
const FOLLOW = /\b(follow|ikuti|ikut kami|ikut saya)\b/i;
// the caption's definitions paragraph ("Definisi: term = meaning; ..." / "Definition: ..."): kept with the follow line and the hashtags
// when a caption is trimmed, and on the last post of a Threads chain (Wan, 22 Nov 2026). Twin of _DEFS in caption_fit.py.
const DEFS = /^\s*(?:definisi|definition)s?\s*:/i;
const DEFS_MAX = 700;
const units = (t) => String(t ?? "").length;
const paragraphs = (t) => String(t ?? "").trim().split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
const join = (a) => a.join("\n\n");

function split(para, limit) {
  if (units(para) <= limit) return [para, ""];
  let best = 0;
  for (const m of para.matchAll(/[.!?…](?=\s)|\n/g)) {
    const end = m[0] === "\n" ? m.index : m.index + m[0].length;
    if (units(para.slice(0, end).trimEnd()) > limit) break;
    best = end;
  }
  if (!best) {
    for (const m of para.matchAll(/\s+/g)) {
      if (units(para.slice(0, m.index)) > limit) break;
      best = m.index;
    }
  }
  if (!best) best = limit;
  return [para.slice(0, best).trimEnd(), para.slice(best).trim()];
}

function tailOf(paras) {
  const body = [...paras];
  const tail = [];
  while (body.length > 1 && (TAGS_ONLY.test(body[body.length - 1]) || (FOLLOW.test(body[body.length - 1]) && units(body[body.length - 1]) <= 200)
    || (DEFS.test(body[body.length - 1]) && units(body[body.length - 1]) <= DEFS_MAX))) {
    tail.unshift(body.pop());
  }
  return [body, tail];
}

function trimTags(tags, room) {
  let out = "";
  for (const tag of tags.split(/\s+/).filter(Boolean)) {
    const next = out ? `${out} ${tag}` : tag;
    if (units(next) > room) break;
    out = next;
  }
  return out;
}

export function fitCaption(text, limit) {
  const t = String(text ?? "");
  if (!limit || units(t) <= limit) return t;
  const [body, tail] = tailOf(paragraphs(t));
  while (body.length > 1 && units(join([...body, ...tail])) > limit) body.pop();
  let out = join([...body, ...tail]);
  if (units(out) <= limit) return out;
  while (tail.length && units(join([...body, ...tail])) > limit) {
    const last = tail[tail.length - 1];
    const room = limit - units(join([...body, ...tail.slice(0, -1)])) - 2;
    const short = TAGS_ONLY.test(last) && room > 0 ? trimTags(last, room) : "";
    if (short) { tail[tail.length - 1] = short; break; }
    tail.pop();
  }
  out = join([...body, ...tail]);
  if (units(out) <= limit) return out;
  const room = limit - (tail.length ? units(join(tail)) + 2 : 0);
  return room > 20 ? join([split(body[0], room)[0], ...tail]) : split(body[0], limit)[0];
}

export function fitThread(text, limit = 500, parts = 5) {
  const t = String(text ?? "");
  const explicit = threadParts(t, SEP);
  if (explicit.length > 1) {
    if (explicit.length <= parts && explicit.every((p) => units(p) <= limit)) return t;
  } else if (units(t) <= limit) return t;
  const flat = (explicit.length > 1 ? explicit : [t]).flatMap(paragraphs);
  const [body, tail] = tailOf(flat);
  const tags = tail.filter((x) => TAGS_ONLY.test(x)).join(" ");
  const follow = tail.filter((x) => !TAGS_ONLY.test(x));
  const pieces = [];
  for (let p of [...body, ...follow]) {
    while (units(p) > limit) { const [head, rest] = split(p, limit); pieces.push(head); p = rest; }
    if (p) pieces.push(p);
  }
  const hookAlone = explicit.length <= 1;
  let posts = [];
  for (const u of pieces) {
    if (posts.length && !(hookAlone && posts.length === 1) && units(posts[posts.length - 1]) + 2 + units(u) <= limit) posts[posts.length - 1] += `\n\n${u}`;
    else posts.push(u);
  }
  if (posts.length > parts) {
    let keep = posts.slice(parts).filter((p) => FOLLOW.test(p));
    // the definitions go on the LAST post, and the body gives way to them, never the other way round
    const defs = posts.slice(parts).flatMap((p) => p.split(/\n\s*\n/)).filter((para) => DEFS.test(para) && units(para) <= DEFS_MAX);
    posts = posts.slice(0, parts);
    if (defs.length) {
      keep = keep.flatMap((p) => p.split(/\n\s*\n/)).filter((para) => FOLLOW.test(para));
      let reserve = [...defs.slice(0, 1), ...keep.slice(-1)].join("\n\n");
      while (units(posts[posts.length - 1]) + 2 + units(reserve) > limit) {
        const paras = posts[posts.length - 1].split("\n\n");
        if (paras.length > 1) posts[posts.length - 1] = paras.slice(0, -1).join("\n\n");
        else if (posts.length > 1) posts.pop();
        else { reserve = units(defs[0]) <= limit ? defs[0] : ""; break; }
      }
      if (reserve && units(posts[posts.length - 1]) + 2 + units(reserve) <= limit) posts[posts.length - 1] += `\n\n${reserve}`;
    } else if (keep.length && units(posts[posts.length - 1]) + 2 + units(keep[keep.length - 1]) <= limit) posts[posts.length - 1] += `\n\n${keep[keep.length - 1]}`;
  }
  if (tags && posts.length) {
    const room = limit - units(posts[posts.length - 1]) - 2;
    const short = room > 0 ? trimTags(tags, room) : "";
    if (short) posts[posts.length - 1] += `\n\n${short}`;
  }
  return posts.join(`\n\n${SEP}\n\n`);
}

export function limitOf(stream, platform) {
  if (platform === "tiktok") return { max: TIKTOK_MAX };
  const lim = (LIMITS[stream || "regulab"] || {})[platform];
  return lim && lim.max ? lim : null;
}

export function fitFor(text, platform, stream) {
  const lim = limitOf(stream, platform);
  if (!lim || typeof text !== "string") return text;
  return lim.parts ? fitThread(text, lim.max, lim.parts) : fitCaption(text, lim.max);
}

/** Every caption of a post ({lang: {platform: caption}}) inside its limit; `keep` names platforms left as they are (a channel a
 * platform already holds). */
export function fitText(text, stream, keep = []) {
  if (!text || typeof text !== "object") return text;
  const out = {};
  for (const [lg, inner] of Object.entries(text)) {
    out[lg] = inner && typeof inner === "object"
      ? Object.fromEntries(Object.entries(inner).map(([p, v]) => [p, keep.includes(p) ? v : fitFor(v, p, stream)]))
      : inner;
  }
  return out;
}

/** The platforms of one language whose caption would be shortened. */
export function overLimit(byPlat, stream) {
  return Object.entries(byPlat || {}).filter(([p, v]) => typeof v === "string" && fitFor(v, p, stream) !== v).map(([p]) => p);
}

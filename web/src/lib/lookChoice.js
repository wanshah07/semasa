/* Which slide design is offered and which is the default (Wan, 8 Nov 2026: "allow to remove slide design", and the new Image look
   as the default). Pure rules with no imports, so web/lookChoice.test.mjs runs them under Node.

   A built-in design can be REMOVED from the picker: it is hidden, never deleted. Its drawing code stays, so a draft that already
   uses it still re-renders, and it comes back with one click. The list lives in semasa_settings.default_design.hidden (an existing
   row, so no SQL). At least one built-in design always stays: the picker is never empty. */
export const BUILTIN_LOOKS = ["classic", "hand", "grid", "era", "photo", "image"];
export const DEFAULT_LOOK = "image";

export const hiddenOf = (v) => (Array.isArray(v) ? v.filter((k) => BUILTIN_LOOKS.includes(k)) : []);

/** The built-in looks offered, in order: the hidden ones are left out, unless that would leave none. */
export function offered(all, hidden) {
  const h = hiddenOf(hidden), keep = all.filter((l) => !h.includes(l.k));
  return keep.length ? keep : all;
}

/** The hidden list after asking to hide `key`. The last offered design cannot be hidden: the same list comes back. */
export function hide(hidden, key, all = BUILTIN_LOOKS) {
  const h = hiddenOf(hidden);
  if (h.includes(key) || !BUILTIN_LOOKS.includes(key)) return h;
  const left = all.filter((k) => k !== key && !h.includes(k));
  return left.length ? [...h, key] : h;
}
export const restore = (hidden, key) => hiddenOf(hidden).filter((k) => k !== key);

/** The look a new post starts on: the default saved design when there is one, else Image, else the first look still offered. */
export function startLook({ designs = [], defaultId = "", hidden = [] } = {}) {
  if (defaultId && designs.some((d) => d.id === defaultId)) return `d:${defaultId}`;
  const h = hiddenOf(hidden);
  if (!h.includes(DEFAULT_LOOK)) return DEFAULT_LOOK;
  return BUILTIN_LOOKS.find((k) => !h.includes(k)) || DEFAULT_LOOK;
}

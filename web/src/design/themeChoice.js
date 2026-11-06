/* Which theme shows. No pick means the phone or computer decides: dark mode gets Noir, light gets Facerinna. A pick in the
   header wins and is kept. The inline script in index.html repeats this rule before first paint; theme.test.mjs checks the
   two still agree.

   The pick has its own key. The old key, `semasa.theme`, was written on every visit, so a saved "facerinna" cannot tell a
   choice from the default and is read as "no pick". Any other value there was a real choice and carries over. */
export const PICK_KEY = "semasa.themePick";
export const OLD_KEY = "semasa.theme";
export const AUTO = "auto";
export const THEME_IDS = ["facerinna", "noir", "regulab"];

export const deviceTheme = (dark) => (dark ? "noir" : "facerinna");

export const resolveTheme = (pick, dark) => (THEME_IDS.includes(pick) ? pick : deviceTheme(dark));

/* `store` is localStorage or anything with getItem/setItem/removeItem. Returns a theme id or AUTO. */
export function readPick(store) {
  try {
    const pick = store.getItem(PICK_KEY);
    if (THEME_IDS.includes(pick)) return pick;
    const old = store.getItem(OLD_KEY);
    if (old !== null) {
      store.removeItem(OLD_KEY);
      if (old !== "facerinna" && THEME_IDS.includes(old)) {
        store.setItem(PICK_KEY, old);
        return old;
      }
    }
  } catch { /* private mode: follow the device */ }
  return AUTO;
}

export function writePick(store, pick) {
  try {
    if (THEME_IDS.includes(pick)) store.setItem(PICK_KEY, pick);
    else store.removeItem(PICK_KEY);
  } catch { /* private mode: the pick lasts until the tab closes */ }
}

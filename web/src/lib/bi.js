/* The page's language for code that is not a component and cannot import the provider (lib/i18n.jsx is JSX, which a Node test
   cannot load): `bi(bm, en)` returns the one the page is showing. lib/i18n.jsx writes the choice to globalThis.__semasaLang
   whenever it changes. A message thrown from a library is built when it is thrown, so it is in the language at that moment.
   Wan, 11 Nov 2026: "if in english version, all must write in english, same goes to malay": these messages used to carry both
   (one string holding both languages). */
export const langNow = () => (typeof globalThis !== "undefined" && globalThis.__semasaLang === "en" ? "en" : "bm");
export const bi = (bm, en) => (langNow() === "en" ? en : bm);

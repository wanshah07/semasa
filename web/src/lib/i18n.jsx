import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/* The page speaks Malay or English (Wan, 25 Sep 2026: "can make system can choose english or malay").
 *
 * Every string is written at its call site in BOTH languages, Malay first:
 *     t("Simpan", "Save")
 *     t("{n} soalan", "{n} questions", { n })
 *     t("{n} soalan", ["{n} question", "{n} questions"], { n })      English singular/plural, chosen by n
 * so nothing can be missing from a dictionary and a reviewer reads both versions side by side. Malay is the
 * default, and a Malaysian Malay string is never machine-made: Malaysian BM only (boleh, ubat, syarikat).
 *
 * Helpers outside React (timeAgo, day names) read `currentLang()`. The provider sits above <App/>, and App reads
 * the context, so a switch re-renders the whole page.
 *
 * What does NOT switch: the words the writers produce (captions, FAQ answers — those have their own BM/EN), the
 * compliance messages (one shared rulebook with the Python publisher, in English), and log titles, which the
 * database writes in Malay: LogTab translates their fixed openings. */

const KEY = "semasa.lang";
let current = "bm";

export const currentLang = () => current;

const english = (en, vars) => (Array.isArray(en) ? en[Number(vars?.n) === 1 ? 0 : 1] : en);

export function fill(text, vars) {
  if (!vars) return text;
  return String(text).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

/** The same as `t`, for code that is not a component. */
export function tr(bm, en, vars) {
  return fill(current === "en" && en != null ? english(en, vars) : bm, vars);
}

function initial() {
  try {
    const saved = window.localStorage.getItem(KEY);
    if (saved === "en" || saved === "bm") return saved;
  } catch { /* private mode or blocked storage: Malay */ }
  return "bm";
}

const LangContext = createContext({ lang: "bm", setLang: () => {}, t: (bm, _en, vars) => fill(bm, vars) });

export function LangProvider({ children }) {
  const [lang, setLangState] = useState(() => (current = initial()));
  const setLang = useCallback((next) => {
    const v = next === "en" ? "en" : "bm";
    current = v;
    setLangState(v);
    try { window.localStorage.setItem(KEY, v); } catch { /* the choice lasts this visit only */ }
  }, []);
  useEffect(() => { document.documentElement.lang = lang === "en" ? "en" : "ms"; }, [lang]);
  const t = useCallback((bm, en, vars) => fill(lang === "en" && en != null ? english(en, vars) : bm, vars), [lang]);
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  current = lang;
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export const useLang = () => useContext(LangContext);

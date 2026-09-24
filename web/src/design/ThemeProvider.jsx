import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import "./tokens.css";
import "./themes/facerinna.css";
import "./themes/noir.css";
import "./themes/regulab.css";

/* Add a theme: write themes/<name>.css, import it above, add its name here. That is the whole procedure. */
export const THEMES = [
  { id: "facerinna", label: "Facerinna" },
  { id: "noir", label: "Noir" },
  { id: "regulab", label: "Regulab" },
];

const KEY = "semasa.theme";
const ThemeCtx = createContext({ theme: "facerinna", setTheme: () => {} });

function readSaved() {
  try {
    const t = localStorage.getItem(KEY);
    return THEMES.some((x) => x.id === t) ? t : "facerinna";
  } catch {
    return "facerinna";
  }
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readSaved);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(KEY, theme); } catch { /* private mode: fine */ }
  }, [theme]);
  const setTheme = useCallback((t) => setThemeState(THEMES.some((x) => x.id === t) ? t : "facerinna"), []);
  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export const useTheme = () => useContext(ThemeCtx);

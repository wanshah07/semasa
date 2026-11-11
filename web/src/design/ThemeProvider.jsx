import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import "./tokens.css";
import "./themes/facerinna.css";
import "./themes/noir.css";
import "./themes/regulab.css";
import "./themes/supabase.css";
import "./themes/supabase-gelap.css";
import "./themes/mint.css";
import "./themes/sakura.css";
import "./themes/lavender.css";
import "./themes/matahari.css";
import "./themes/batu.css";
import "./themes/midnight.css";
import "./themes/hutan.css";
import "./themes/bara.css";
import "./themes/mawar.css";
import "./themes/lautan.css";
import "./themes/arang.css";
import "./themes/kopi.css";
import { AUTO, THEME_IDS, readPick, resolveTheme, writePick } from "./themeChoice";
import { syncThemeColor } from "../lib/pwa";

/* Add a theme: write themes/<name>.css, import it above, add its name here and to THEME_IDS in themeChoice.js and the
   inline script in index.html. */
export const THEMES = [
  { id: "facerinna", label: "Facerinna" },
  { id: "noir", label: "Noir" },
  { id: "regulab", label: "Regulab" },
  { id: "supabase", label: "Supabase" },
  { id: "supabase-gelap", label: "Supabase Gelap" },
  { id: "mint", label: "Mint" },
  { id: "sakura", label: "Sakura" },
  { id: "lavender", label: "Lavender" },
  { id: "matahari", label: "Matahari" },
  { id: "batu", label: "Batu" },
  { id: "midnight", label: "Midnight" },
  { id: "hutan", label: "Hutan" },
  { id: "bara", label: "Bara" },
  { id: "mawar", label: "Mawar" },
  { id: "lautan", label: "Lautan" },
  { id: "arang", label: "Arang" },
  { id: "kopi", label: "Kopi" },
];

const QUERY = "(prefers-color-scheme: dark)";
const ThemeCtx = createContext({ theme: "facerinna", pick: AUTO, setTheme: () => {} });

const store = () => (typeof localStorage === "undefined" ? null : localStorage);
const deviceDark = () => typeof matchMedia === "function" && matchMedia(QUERY).matches;

export function ThemeProvider({ children }) {
  const [pick, setPick] = useState(() => (store() ? readPick(store()) : AUTO));
  const [dark, setDark] = useState(deviceDark);

  // follow the device live: turning dark mode on in the phone's settings changes the app without a reload
  useEffect(() => {
    if (typeof matchMedia !== "function") return undefined;
    const mq = matchMedia(QUERY);
    const on = (e) => setDark(e.matches);
    setDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const theme = resolveTheme(pick, dark);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    syncThemeColor();   // the iPhone status bar follows the theme's own background (lib/pwa.js)
  }, [theme]);

  const setTheme = useCallback((t) => {
    const next = THEME_IDS.includes(t) ? t : AUTO;
    setPick(next);
    if (store()) writePick(store(), next);
  }, []);
  const value = useMemo(() => ({ theme, pick, setTheme }), [theme, pick, setTheme]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export const useTheme = () => useContext(ThemeCtx);

/* Semasa as an app on Wan's iPhone (Wan, 7 Nov 2026: "create friendly apps mobile version so I can install in iphone").
   It is a Progressive Web App added to the Home Screen from Safari: no App Store, no native build. This file holds the
   pure rules (tested by pwa.test.mjs without a browser) and the two browser hooks: registering the service worker and
   keeping the status bar the colour of the theme. */

export const INSTALL_HINT_KEY = "semasa.installHint.dismissed";

/** iPhone, iPod or iPad. iPadOS 13+ reports itself as a Mac, so a "Mac" with a touch screen is an iPad. */
export function isIos({ userAgent = "", platform = "", maxTouchPoints = 0 } = {}) {
  if (/iPhone|iPad|iPod/.test(userAgent)) return true;
  return platform === "MacIntel" && maxTouchPoints > 1;
}

/** Safari itself, where Share → Add to Home Screen lives. Chrome, Firefox, Edge and Opera on iOS and the apps that open
    links inside themselves (Facebook, Instagram, LINE, Telegram) also say "Safari" in their user agent, so they are named. */
export function isIosSafari(nav = {}) {
  const ua = nav.userAgent || "";
  if (!isIos(nav)) return false;
  if (!/Safari\//.test(ua) || !/AppleWebKit\//.test(ua)) return false;
  return !/CriOS|FxiOS|EdgiOS|OPiOS|OPT\/|GSA\/|FBAN|FBAV|Instagram|Line\/|Telegram|DuckDuckGo/.test(ua);
}

/** Opened from the Home Screen icon: iOS sets navigator.standalone, other browsers answer the display-mode query. */
export function isStandalone({ navigatorStandalone = false, displayModeStandalone = false } = {}) {
  return navigatorStandalone === true || displayModeStandalone === true;
}

/** The "Install on iPhone" hint shows in Safari on iOS, until it is installed or the hint is closed once. */
export function shouldShowInstallHint({ nav = {}, standalone = false, dismissed = false } = {}) {
  return isIosSafari(nav) && !standalone && !dismissed;
}

/** What the running browser says, in the shape the rules above read. Safe where window does not exist. */
export function browserFacts() {
  if (typeof window === "undefined" || typeof navigator === "undefined") return { nav: {}, standalone: false };
  let displayModeStandalone = false;
  try { displayModeStandalone = window.matchMedia("(display-mode: standalone)").matches; } catch { /* old browser */ }
  return {
    nav: { userAgent: navigator.userAgent || "", platform: navigator.platform || "", maxTouchPoints: navigator.maxTouchPoints || 0 },
    standalone: isStandalone({ navigatorStandalone: navigator.standalone, displayModeStandalone }),
  };
}

export function readDismissed(store) {
  try { return store?.getItem(INSTALL_HINT_KEY) === "1"; } catch { return false; }   // a private window can refuse storage
}
export function writeDismissed(store) {
  try { store?.setItem(INSTALL_HINT_KEY, "1"); } catch { /* the hint comes back next time; nothing else is lost */ }
}

/** "251 253 255" (a theme token, see design/tokens.css) → "#fbfdff". Null for anything else. */
export function themeColorFrom(token) {
  const parts = String(token || "").trim().split(/[\s,]+/).map(Number);
  if (parts.length < 3 || parts.slice(0, 3).some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return null;
  return `#${parts.slice(0, 3).map((n) => n.toString(16).padStart(2, "0")).join("")}`;
}

/** The status bar (iOS) and the title bar (Android) take the page's own background, so Noir is dark up there too.
    Called by the ThemeProvider after every theme change. */
export function syncThemeColor() {
  if (typeof document === "undefined") return;
  const hex = themeColorFrom(getComputedStyle(document.documentElement).getPropertyValue("--c-bg"));
  if (!hex) return;
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.appendChild(meta);
  }
  meta.content = hex;
}

/** A new worker took over while the app was open. Reload only when that is safe: never on the very first install (the
    page did not change), and only after the app sat in the background a while, so a half-written caption is not lost to
    a reload in the middle of typing. A reopened app is a fresh start in the user's mind anyway. */
export const RELOAD_AFTER_HIDDEN_MS = 60_000;
export function shouldReloadForUpdate({ hadController = false, updated = false, hiddenMs = 0 } = {}) {
  return hadController && updated && hiddenMs >= RELOAD_AFTER_HIDDEN_MS;
}

/** Production builds only: in `npm run dev` there is no dist/sw.js, and a worker would cache Vite's live modules. */
export function registerServiceWorker() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator) || !window.isSecureContext) return;
  // the first controller a page ever gets is the first install (nothing changed); any later one is a new deploy
  let hadController = Boolean(navigator.serviceWorker.controller);
  let updated = false;
  let hiddenAt = 0;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController) updated = true;
    hadController = true;
  });
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js", { scope: "./" }).then((reg) => {
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "hidden") { hiddenAt = Date.now(); return; }
        const hiddenMs = hiddenAt ? Date.now() - hiddenAt : 0;
        if (shouldReloadForUpdate({ hadController, updated, hiddenMs })) { window.location.reload(); return; }
        // an app left open in the background never navigates, so it asks for a new deploy each time it comes back
        reg.update().catch(() => {});
      });
    }).catch(() => { /* no worker: the site works exactly as before, just without the offline copy */ });
  });
}

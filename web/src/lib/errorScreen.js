/* What the error screen says and does (Wan, 8 Nov 2026: "add the error screen", after one realtime error blanked the whole app).
   Pure rules with no imports, so web/errorScreen.test.mjs runs them under Node. The screen itself is components/ErrorBoundary.jsx. */

/** One short, safe line about a crash: the error's own message, collapsed to one line and cut. Never a stack, never a token:
    a long message is cut, and anything that looks like a bearer token or a JWT is blanked. */
export function errorLine(error, max = 200) {
  const raw = error && typeof error === "object" && "message" in error ? error.message : error;
  let s = String(raw == null ? "" : raw).replace(/\s+/g, " ").trim();
  s = s.replace(/eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]*/g, "[token]").replace(/\b(Bearer|apikey|key)[=:\s]+[\w.-]{12,}/gi, "$1 [hidden]");
  if (!s) return "Unknown error";
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/** The address to open for "Go to Papan": the same page with no #segment, so an app that reopens on the segment that
    crashed starts from the home view. */
export function homeUrl(href) {
  try {
    const u = new URL(href);
    u.hash = "";
    return u.toString();
  } catch { return href; }
}

/** Whether a cache name belongs to Semasa's own service worker (src/lib/pwa.js, public sw.js): the shell caches and the asset cache. */
export const isAppCache = (name) => /^semasa-(shell-|assets)/.test(String(name || ""));

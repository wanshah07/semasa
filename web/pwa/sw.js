/* Semasa's service worker: the installed iPhone app opens from its own cache and still shows the page with no signal.
   This file is a TEMPLATE. vite.config.js (semasaServiceWorker) writes it to dist/sw.js at build time with BUILD set to a
   hash of the build and PRECACHE set to the app shell (index.html, the entry script, its CSS and the vendor chunks it
   imports). A new deploy therefore changes the bytes of sw.js, which is what makes a browser install the new worker.

   What it never touches, so no stale or private data can be served from a cache:
   - anything on another origin: Supabase (REST, auth, storage, realtime, functions), Google Fonts, Unsplash, every API;
   - any request that is not a GET (sign-in, saves, uploads);
   - a same-origin path that looks like a Supabase route, in case the site is ever put behind a proxy.

   index.html is network-first and asked for with `cache: "no-cache"`, so a new deploy is seen on the next open whenever
   there is a connection; the cached copy is only the offline fallback. Hashed files under assets/ never change, so they
   are cache-first. */
const BUILD = "dev";
const PRECACHE = [];

const SHELL = `semasa-shell-${BUILD}`;
const ASSETS = "semasa-assets";        // hashed names never collide, so one cache serves every build
const ASSET_LIMIT = 160;               // ~ two builds of chunks; the oldest go first
const API_PATH = /\/(rest|auth|storage|functions|realtime|graphql)\/v1\//;

/** How a request is answered. Pure, so pwa.test.mjs can run it in node without a browser.
    Returns "skip" (the browser fetches it as if no worker existed), "navigate", "asset" or "static". */
function routeOf(request, scope) {
  if (request.method !== "GET") return "skip";
  let url;
  try { url = new URL(request.url); } catch { return "skip"; }
  const base = new URL(scope);
  if (url.origin !== base.origin) return "skip";
  if (API_PATH.test(url.pathname)) return "skip";
  if (!url.pathname.startsWith(base.pathname)) return "skip";
  if (request.mode === "navigate") return "navigate";
  if (url.pathname.startsWith(`${base.pathname}assets/`)) return "asset";
  if (url.pathname.endsWith("/sw.js")) return "skip";
  return "static";
}

/** Whether a navigation's answer may become the offline copy of the app. Only a real page of this site: an OK, same-origin
    answer whose content type is HTML. Opening manifest.webmanifest, an icon or a JSON file in the browser is a navigation too,
    and saving that as the shell left the installed app opening a file instead of itself with no signal. Pure (pwa.test.mjs). */
function isShellPage(res) {
  if (!res || !res.ok || res.type !== "basic") return false;
  const type = (res.headers && typeof res.headers.get === "function" && res.headers.get("content-type")) || "";
  return /\btext\/html\b/i.test(type);
}

async function trim(cache, max) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function navigate(request) {
  const shell = await caches.open(SHELL);
  const index = new URL("./", self.registration.scope).href;
  try {
    const res = await fetch(request, { cache: "no-cache" });
    // keep the newest index.html as the offline copy (only a real HTML page: a 404, an opaque answer or a file is not kept)
    if (isShellPage(res)) shell.put(index, res.clone());
    return res;
  } catch (err) {
    const hit = (await shell.match(index)) || (await shell.match(new URL("./index.html", self.registration.scope).href));
    if (hit) return hit;
    throw err;
  }
}

async function asset(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok && res.type === "basic") {
    const cache = await caches.open(ASSETS);
    await cache.put(request, res.clone());
    trim(cache, ASSET_LIMIT);
  }
  return res;
}

// icons, the manifest, card fonts and grounds: fresh when online, from the cache when not
async function staticFile(request) {
  try {
    const res = await fetch(request);
    if (res.ok && res.type === "basic") (await caches.open(SHELL)).put(request, res.clone());
    return res;
  } catch (err) {
    const hit = await caches.match(request);
    if (hit) return hit;
    throw err;
  }
}

if (typeof self !== "undefined" && typeof self.addEventListener === "function" && self.registration) {
  self.addEventListener("install", (event) => {
    event.waitUntil((async () => {
      const cache = await caches.open(SHELL);
      // one missing file must not stop the worker installing: the next deploy tries again
      await Promise.all(PRECACHE.map((p) => cache.add(new Request(new URL(p, self.registration.scope), { cache: "reload" })).catch(() => {})));
      // no prompt (Wan installs it for himself): the new worker takes over at once, and the page reloads on its next open
      await self.skipWaiting();
    })());
  });

  self.addEventListener("activate", (event) => {
    event.waitUntil((async () => {
      const names = await caches.keys();
      await Promise.all(names.filter((n) => n.startsWith("semasa-shell-") && n !== SHELL).map((n) => caches.delete(n)));
      await self.clients.claim();
    })());
  });

  self.addEventListener("fetch", (event) => {
    const route = routeOf(event.request, self.registration.scope);
    if (route === "skip") return;
    if (route === "navigate") event.respondWith(navigate(event.request));
    else if (route === "asset") event.respondWith(asset(event.request));
    else event.respondWith(staticFile(event.request));
  });
}

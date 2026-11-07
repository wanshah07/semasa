/* The iPhone app (Wan, 7 Nov 2026): the install rules in src/lib/pwa.js, the bottom bar's places, the manifest and the
   service worker's routing. The worker is run in a bare node context (no `self`), so routeOf can be called directly and
   the event listeners never attach. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { INSTALL_HINT_KEY, isIos, isIosSafari, isStandalone, readDismissed, shouldReloadForUpdate, shouldShowInstallHint,
  themeColorFrom, writeDismissed, RELOAD_AFTER_HIDDEN_MS } from "./src/lib/pwa.js";
import { mobileTabsOf, tabsOf } from "./src/lib/tabs.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

const UA = {
  iphoneSafari: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
  iphoneChrome: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1",
  iphoneFirefox: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/132.0 Mobile/15E148 Safari/605.1.15",
  iphoneInstagram: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 357.0.0 (iPhone15,3; iOS 18_1)",
  iphoneFacebook: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/490.0] Safari/604.1",
  ipadOs: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
  macSafari: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
  android: "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
};
const nav = (userAgent, extra = {}) => ({ userAgent, platform: "iPhone", maxTouchPoints: 5, ...extra });

t("isIos: iPhone, and an iPad that calls itself a Mac (touch screen); never a real Mac or Android", () => {
  assert.equal(isIos(nav(UA.iphoneSafari)), true);
  assert.equal(isIos({ userAgent: UA.ipadOs, platform: "MacIntel", maxTouchPoints: 5 }), true);
  assert.equal(isIos({ userAgent: UA.macSafari, platform: "MacIntel", maxTouchPoints: 0 }), false);
  assert.equal(isIos({ userAgent: UA.android, platform: "Linux armv8l", maxTouchPoints: 5 }), false);
  assert.equal(isIos(), false);
});
t("isIosSafari: Safari only; Chrome, Firefox and in-app browsers on iOS are not where Add to Home Screen is explained", () => {
  assert.equal(isIosSafari(nav(UA.iphoneSafari)), true);
  assert.equal(isIosSafari({ userAgent: UA.ipadOs, platform: "MacIntel", maxTouchPoints: 5 }), true);
  for (const k of ["iphoneChrome", "iphoneFirefox", "iphoneInstagram", "iphoneFacebook"]) assert.equal(isIosSafari(nav(UA[k])), false, k);
  assert.equal(isIosSafari({ userAgent: UA.android, platform: "Linux", maxTouchPoints: 5 }), false);
});
t("isStandalone: iOS's navigator.standalone or the display-mode query; anything else is a browser tab", () => {
  assert.equal(isStandalone({ navigatorStandalone: true }), true);
  assert.equal(isStandalone({ displayModeStandalone: true }), true);
  assert.equal(isStandalone({ navigatorStandalone: undefined, displayModeStandalone: false }), false);
  assert.equal(isStandalone({ navigatorStandalone: "yes" }), false, "only a real true counts");
  assert.equal(isStandalone(), false);
});
t("shouldShowInstallHint: Safari on iOS, not installed, not closed before", () => {
  assert.equal(shouldShowInstallHint({ nav: nav(UA.iphoneSafari) }), true);
  assert.equal(shouldShowInstallHint({ nav: nav(UA.iphoneSafari), standalone: true }), false);
  assert.equal(shouldShowInstallHint({ nav: nav(UA.iphoneSafari), dismissed: true }), false);
  assert.equal(shouldShowInstallHint({ nav: nav(UA.iphoneChrome) }), false);
  assert.equal(shouldShowInstallHint({ nav: { userAgent: UA.android } }), false);
  assert.equal(shouldShowInstallHint(), false);
});
t("the dismissal is remembered, and a storage that throws (private window) neither crashes nor hides the hint", () => {
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  assert.equal(readDismissed(store), false);
  writeDismissed(store);
  assert.equal(mem.get(INSTALL_HINT_KEY), "1");
  assert.equal(readDismissed(store), true);
  const broken = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); } };
  assert.equal(readDismissed(broken), false);
  assert.doesNotThrow(() => writeDismissed(broken));
  assert.equal(readDismissed(null), false);
});
t("themeColorFrom turns a theme token into the hex the status bar takes", () => {
  assert.equal(themeColorFrom(" 251 253 255"), "#fbfdff");
  assert.equal(themeColorFrom("11  22  32"), "#0b1620");
  assert.equal(themeColorFrom("16,34,47"), "#10222f");
  assert.equal(themeColorFrom(""), null);
  assert.equal(themeColorFrom("var(--x)"), null);
  assert.equal(themeColorFrom("300 0 0"), null);
});
t("a new deploy reloads the app only after it sat in the background, never on the first install", () => {
  const long = RELOAD_AFTER_HIDDEN_MS;
  assert.equal(shouldReloadForUpdate({ hadController: true, updated: true, hiddenMs: long }), true);
  assert.equal(shouldReloadForUpdate({ hadController: true, updated: true, hiddenMs: long - 1 }), false, "a quick app switch keeps a half-typed caption");
  assert.equal(shouldReloadForUpdate({ hadController: false, updated: true, hiddenMs: long }), false);
  assert.equal(shouldReloadForUpdate({ hadController: true, updated: false, hiddenMs: long }), false);
});
t("the bottom bar: five real pages, each lit by its own page, Video also by the video library", () => {
  const items = mobileTabsOf((bm) => bm);
  const pages = new Set(tabsOf((bm) => bm).map((p) => p.id));
  assert.equal(items.length, 5);
  assert.deepEqual(items.map((i) => i.id), ["papan", "idea", "post", "video", "chat"]);
  for (const i of items) {
    assert.ok(pages.has(i.id), i.id);
    assert.ok(i.match.includes(i.id) && i.match.every((m) => pages.has(m)), i.id);
    assert.ok(i.icon, i.id);
    assert.ok(i.label.length <= 8, `${i.label}: five labels must fit 375 px`);
  }
  assert.ok(items.find((i) => i.id === "video").match.includes("video-lib"));
  assert.deepEqual(mobileTabsOf((bm, en) => en).map((i) => i.label), ["Home", "Idea", "Post", "Video", "Chat"]);
});

const manifest = JSON.parse(readFileSync(new URL("./public/manifest.webmanifest", import.meta.url), "utf8"));
t("the manifest: standalone, relative start_url and scope (the same build serves /semasa/ and the custom domain's root)", () => {
  assert.equal(manifest.name, "Semasa");
  assert.equal(manifest.short_name, "Semasa");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "./");
  assert.equal(manifest.scope, "./");
  assert.match(manifest.theme_color, /^#[0-9A-F]{6}$/i);
  assert.match(manifest.background_color, /^#[0-9A-F]{6}$/i);
  const sizes = (purpose) => manifest.icons.filter((i) => i.purpose === purpose).map((i) => i.sizes);
  assert.ok(sizes("any").includes("192x192") && sizes("any").includes("512x512"));
  assert.ok(sizes("maskable").includes("512x512"));
  for (const i of manifest.icons) {
    assert.ok(!i.src.startsWith("/"), `${i.src}: an absolute path breaks under /semasa/`);
    const png = readFileSync(new URL(`./public/${i.src}`, import.meta.url));
    assert.equal(png.readUInt32BE(16), Number(i.sizes.split("x")[0]), `${i.src} is the size it claims`);
  }
});
t("the theme colour in the manifest is the default theme's own background token", () => {
  const tokens = readFileSync(new URL("./src/design/tokens.css", import.meta.url), "utf8");
  const bg = /--c-bg:\s*([\d\s]+);/.exec(tokens)[1];
  assert.equal(manifest.background_color.toLowerCase(), themeColorFrom(bg));
});
t("index.html carries the iOS tags and links the manifest relatively", () => {
  const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
  assert.match(html, /viewport-fit=cover/);
  assert.match(html, /<link rel="manifest" href="\.\/manifest\.webmanifest"/);
  assert.match(html, /<link rel="apple-touch-icon" sizes="180x180" href="\.\/icons\/apple-touch-icon\.png"/);
  for (const name of ["apple-mobile-web-app-capable", "mobile-web-app-capable", "apple-mobile-web-app-status-bar-style", "apple-mobile-web-app-title", "theme-color"]) {
    assert.match(html, new RegExp(`<meta name="${name}" content="[^"]+"`), name);
  }
});

// the worker template, run without a `self`: only its functions are defined
const swSrc = readFileSync(new URL("./pwa/sw.js", import.meta.url), "utf8");
const ctx = vm.createContext({ URL });
vm.runInContext(`${swSrc}\nthis.routeOf = routeOf;\nthis.isShellPage = isShellPage;`, ctx);
const SCOPE = "https://socialmedia.kkmhalalconsultant.com/";
const req = (url, extra = {}) => ({ url, method: "GET", mode: "cors", ...extra });
t("the worker never answers Supabase, auth, storage, other sites or anything but a GET", () => {
  const skip = [
    req("https://abcd.supabase.co/rest/v1/semasa_posts?select=*"),
    req("https://abcd.supabase.co/auth/v1/token?grant_type=password", { method: "POST" }),
    req("https://abcd.supabase.co/storage/v1/object/public/media/a.png"),
    req("https://abcd.supabase.co/functions/v1/semasa-chat", { method: "POST" }),
    req("https://fonts.googleapis.com/css2?family=Inter"),
    req("https://images.unsplash.com/photo-1"),
    req(`${SCOPE}rest/v1/anything`),            // a same-origin path shaped like Supabase (a proxy) is still left alone
    req(`${SCOPE}auth/v1/callback`, { mode: "navigate" }),
    req(`${SCOPE}assets/index-abc.js`, { method: "POST" }),
    req(`${SCOPE}sw.js`),
  ];
  for (const r of skip) assert.equal(ctx.routeOf(r, SCOPE), "skip", `${r.method} ${r.url}`);
});
t("the worker: pages are network-first navigations, hashed files cache-first, the rest static", () => {
  assert.equal(ctx.routeOf(req(SCOPE, { mode: "navigate" }), SCOPE), "navigate");
  assert.equal(ctx.routeOf(req(`${SCOPE}#post`, { mode: "navigate" }), SCOPE), "navigate");
  assert.equal(ctx.routeOf(req(`${SCOPE}assets/index-abc.js`), SCOPE), "asset");
  assert.equal(ctx.routeOf(req(`${SCOPE}manifest.webmanifest`), SCOPE), "static");
  assert.equal(ctx.routeOf(req(`${SCOPE}icons/icon-192.png`), SCOPE), "static");
});
t("only a real HTML page becomes the offline app: opening the manifest, an icon or a 404 never replaces it", () => {
  const res = (type, extra = {}) => ({ ok: true, type: "basic", headers: new Map([["content-type", type]]), ...extra });
  assert.equal(ctx.isShellPage(res("text/html; charset=utf-8")), true);
  assert.equal(ctx.isShellPage(res("TEXT/HTML")), true);
  assert.equal(ctx.isShellPage(res("application/manifest+json")), false, "manifest.webmanifest opened in the browser");
  assert.equal(ctx.isShellPage(res("image/png")), false);
  assert.equal(ctx.isShellPage(res("application/json")), false);
  assert.equal(ctx.isShellPage(res("")), false, "no content type is not a page");
  assert.equal(ctx.isShellPage(res("text/html", { ok: false, status: 404 })), false);
  assert.equal(ctx.isShellPage(res("text/html", { type: "opaque" })), false);
  assert.equal(ctx.isShellPage(null), false);
  assert.match(swSrc, /if \(isShellPage\(res\)\) shell\.put\(index, res\.clone\(\)\);/, "navigate() saves the shell through the check");
});
t("under /semasa/ (github.io) the worker keeps to its own folder", () => {
  const s = "https://wanshah07.github.io/semasa/";
  assert.equal(ctx.routeOf(req(`${s}assets/a.js`), s), "asset");
  assert.equal(ctx.routeOf(req("https://wanshah07.github.io/other-repo/", { mode: "navigate" }), s), "skip");
});
t("the build writes the real BUILD and PRECACHE into the template's two placeholder lines", () => {
  assert.ok(swSrc.includes('const BUILD = "dev";') && swSrc.includes("const PRECACHE = [];"));
  const cfg = readFileSync(new URL("./vite.config.js", import.meta.url), "utf8");
  assert.ok(cfg.includes(`.replace('const BUILD = "dev";'`) && cfg.includes('.replace("const PRECACHE = [];"'));
});
t("the worker is registered in production builds only", () => {
  const main = readFileSync(new URL("./src/main.jsx", import.meta.url), "utf8");
  assert.match(main, /if \(import\.meta\.env\.PROD\) registerServiceWorker\(\);/);
});

console.log(`pwa: ${n} ok`);

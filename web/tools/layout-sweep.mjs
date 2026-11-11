/* Layout sweep (Wan, 11 Nov 2026: "check all ui/ux and no overlap or overflow ... for all mobile, desktop, tv, tablet").
   Opens every tab signed in against a mocked Supabase (empty tables) at phone, small phone, tablet, desktop and TV sizes and
   reports sideways page scroll, anything sticking off the screen outside a scroller, and clipped button or heading text.

     VITE_SUPABASE_URL=https://example.supabase.co VITE_SUPABASE_ANON_KEY=anon npx vite build --outDir /tmp/semasa-sweep
     node tools/layout-sweep.mjs /tmp/semasa-sweep [tab,tab]

   VIEW=phone,tablet limits the sizes; CHAT=1 fills the AI chat with a long conversation (table, code, long link);
   SHOTS=phone:chat,tablet:papan (or SHOTS=all) saves screenshots to SHOT_DIR (default: the system temp folder).
   Not part of `npm test`: it needs a browser. */
import os from "node:os";
import { createRequire } from "node:module"; const { chromium } = createRequire(import.meta.url)("playwright");
import http from "node:http"; import fs from "node:fs"; import path from "node:path";
const DIST = process.argv[2]; const ONLY = (process.argv[3] || "").split(",").filter(Boolean);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webmanifest": "application/manifest+json" };
const srv = http.createServer((q, r) => { let p = path.join(DIST, decodeURIComponent(q.url.split("?")[0])); if (!fs.existsSync(p) || fs.statSync(p).isDirectory()) p = path.join(DIST, "index.html"); r.writeHead(200, { "content-type": types[path.extname(p)] || "application/octet-stream" }); fs.createReadStream(p).pipe(r); }).listen(4319);
const TABS = ["papan","chat","memori","otak","isu","idea","post","hooks","gaya","prestasi","media","media-lib","video","video-lib","motion-skills","design","design-lib","wangian","bil-valorith","wang","bil","crm","syarikat","tech","office","repo","api","stack","resit","langganan","faq","log","dokumen","tetapan"].filter((t) => !ONLY.length || ONLY.includes(t));
const VIEWS_ALL = [["phone", 390, 844], ["phone-small", 360, 740], ["tablet", 820, 1180], ["desktop", 1440, 900], ["tv", 2560, 1440]];
const VIEWS = VIEWS_ALL.filter((v) => !process.env.VIEW || process.env.VIEW.split(",").includes(v[0]));
const user = { id: "00000000-0000-4000-8000-000000000001", aud: "authenticated", role: "authenticated", email: "wan@example.com", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" };
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const session = { access_token: `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ sub: user.id, role: "authenticated", exp: 4102444800 })}.x`, token_type: "bearer", expires_in: 3600, expires_at: 4102444800, refresh_token: "r", user };
const browser = await chromium.launch();
const out = [];
for (const [name, w, h] of VIEWS) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, hasTouch: w < 900, isMobile: w < 500 });
  await ctx.addInitScript((s) => { localStorage.setItem("sb-example-auth-token", JSON.stringify(s)); localStorage.setItem("semasa.lang", "en"); }, session);
  await ctx.route("https://example.supabase.co/**", (route) => {
    const u = route.request().url();
    if (u.includes("/auth/v1/user")) return route.fulfill({ json: user });
    if (u.includes("/auth/v1/")) return route.fulfill({ json: session });
    if (u.includes("semasa_uploaders")) return route.fulfill({ json: { user_id: user.id }, headers: { "content-range": "0-0/1" } });
    if (process.env.CHAT && u.includes("semasa_chat_threads")) { const th = { id: "t1", title: "Notifikasi kosmetik dan tuntutan iklan yang panjang sekali tajuknya", updated_at: "2026-11-11T10:00:00Z", created_at: "2026-11-11T09:00:00Z" }; return route.fulfill({ json: route.request().headers()["accept"]?.includes("vnd.pgrst.object") ? th : [th] }); }
    if (process.env.CHAT && u.includes("semasa_chat_messages")) return route.fulfill({ json: [
      { id: 1, role: "user", content: "Boleh semak tuntutan ini? https://www.npra.gov.my/index.php/en/consumers/safety-information/cancellation-of-notified-cosmetic-products.html?start=20&verylongparameter=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", tools: null, created_at: "2026-11-11T09:00:00Z" },
      { id: 2, role: "assistant", content: "## Ringkasan\n\nNotifikasi **bukan** kelulusan. Rujuk `Guidelines_for_Control_of_Cosmetic_Products_in_Malaysia_Annex_I_Part_8_very_long_identifier_without_spaces`.\n\n| Tuntutan | Keputusan | Rujukan peraturan yang panjang | Cadangan penulisan semula |\n|---|---|---|---|\n| Memutihkan kulit dalam 7 hari | Tidak boleh diterima | Annex I Part 8 | Mencerahkan rupa kulit |\n| Menghilangkan jerawat | Berisiko | Annex I Part 10 | Membantu kulit kelihatan bersih |\n\n```python\ndef very_long_function_name_for_overflow_check(parameter_one, parameter_two, parameter_three, parameter_four):\n    return parameter_one + parameter_two\n```\n\n1. Semak label\n2. Semak iklan\n\nSumber: https://www.npra.gov.my/a/very/long/path/that/does/not/break/naturally/and/keeps/going/and/going/and/going/index.html", tools: [{ name: "web_read", ok: true }], created_at: "2026-11-11T09:00:20Z" },
      { id: 3, role: "user", content: "ok terima kasih, buatkan kapsyen pendek", tools: null, created_at: "2026-11-11T09:01:00Z" },
      { id: 4, role: "assistant", content: "Notifikasi kosmetik bukan cop lulus. Ia cuma makluman kepada NPRA sebelum produk dijual.\n\nSupercalifragilisticexpialidociousSupercalifragilisticexpialidociousSupercalifragilisticexpialidocious", tools: null, created_at: "2026-11-11T09:01:20Z" } ] });
    if (u.includes("/rpc/")) return route.fulfill({ json: null });
    if (u.includes("/rest/v1/")) return route.fulfill({ json: route.request().headers()["accept"]?.includes("vnd.pgrst.object") ? null : [], status: route.request().headers()["accept"]?.includes("vnd.pgrst.object") ? 406 : 200 });
    return route.fulfill({ status: 200, body: "{}" });
  });
  await ctx.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  const page = await ctx.newPage();
  const errs = []; page.on("pageerror", (e) => errs.push(String(e).slice(0, 160)));
  for (const tab of TABS) {
    if (tab === TABS[0]) await page.goto("http://localhost:4319/", { waitUntil: "domcontentloaded", timeout: 20000 });
    await page.evaluate((h) => { window.location.hash = h; }, tab === "papan" ? "" : tab);
    await page.waitForTimeout(1100);
    const r = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      const hscroll = document.documentElement.scrollWidth - vw;
      const bad = [];
      const scrollerOf = (el) => { for (let p = el.parentElement; p; p = p.parentElement) { const s = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(s.overflowX) && p !== document.body && p !== document.documentElement) return p; } return null; };
      for (const el of document.querySelectorAll("button, a, input, select, textarea, h1, h2, h3, p, label, span, td, th, li")) {
        const s = getComputedStyle(el); if (s.display === "none" || s.visibility === "hidden") continue;
        const b = el.getBoundingClientRect(); if (!b.width || !b.height) continue;
        if (s.position === "fixed" && (b.right < 0 || b.left > vw)) continue;
        // sticks out of the screen with no scrolling ancestor to contain it
        if ((b.right > vw + 1 || b.left < -1) && !scrollerOf(el)) bad.push(["offscreen", el.tagName, (el.innerText || el.getAttribute("aria-label") || "").slice(0, 40), Math.round(b.left), Math.round(b.right)]);
        // text clipped inside its own box (no ellipsis, no scroll)
        if (/^(BUTTON|A|LABEL|H1|H2|H3)$/.test(el.tagName) && el.scrollWidth > el.clientWidth + 2 && s.overflowX === "visible" && s.textOverflow !== "ellipsis" && el.children.length === 0) bad.push(["spills", el.tagName, (el.innerText || "").slice(0, 40), el.clientWidth, el.scrollWidth]);
      }
      // anything inside the chat that is wider than the chat column and not inside its own scroller
      const chat = document.querySelector("[data-chat-root]");
      if (chat) { const cb = chat.getBoundingClientRect(); for (const el of chat.querySelectorAll("*")) { const b = el.getBoundingClientRect(); if (b.width && (b.right > cb.right + 1 || b.left < cb.left - 1) && !scrollerOf(el)) { bad.push(["chat-overflow", el.tagName, (el.className || "").toString().slice(0, 50), Math.round(b.left), Math.round(b.right)]); } }
        const ta = chat.querySelector("textarea"); const nav = document.querySelector("nav[aria-label], .tabbar, [data-tabbar]");
        if (ta) { const tb = ta.closest("form")?.getBoundingClientRect() || ta.getBoundingClientRect(); bad.push(["composer", "bottom", String(Math.round(tb.bottom)), Math.round(tb.top), window.innerHeight]); } }
      const title = document.querySelector("h1")?.innerText || "";
      const crashed = /went wrong|Ralat|tidak dapat dibuka/i.test(document.body.innerText.slice(0, 400)) && !title;
      return { hscroll, bad: bad.slice(0, 8), title: title.slice(0, 40), crashed, len: document.body.innerText.length };
    });
    if (process.env.SHOTS && (process.env.SHOTS === "all" || process.env.SHOTS.split(",").includes(`${name}:${tab}`))) await page.screenshot({ path: path.join(process.env.SHOT_DIR || os.tmpdir(), `${name}-${tab}.png`) });
    if (r.hscroll > 1 || r.bad.length || r.crashed || r.len < 40) { out.push({ view: name, tab, ...r }); console.log(JSON.stringify({ view: name, tab, ...r })); } else console.log(`ok ${name} ${tab} "${r.title}"`);
  }
  if (errs.length) out.push({ view: name, pageerrors: [...new Set(errs)].slice(0, 5) });
  await ctx.close();
}
console.log("problem rows:", out.length);
await browser.close(); srv.close();

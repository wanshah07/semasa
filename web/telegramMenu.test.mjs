/* Semasa on Telegram, the button menu (Wan, 16 Nov 2026: "make sure all features appear in telegram semasa button").

   ONE catalogue, rules/telegram_menu.json, holds every button. This file holds it to the page: a tab in src/lib/tabs.js with no
   entry in the catalogue fails, and so does an entry for a tab that is gone, a page in another segment, or a different name.
   It also holds the webhook's copy and renderer (supabase/functions/semasa-telegram/menu_data.js, menu.js) to the catalogue
   and to rules/telegram_menu_cases.json, which is what the worker's renderer draws (backend/tests/test_telegram_menu.py checks
   that half). `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { segmentsOf, tabsOf } from "./src/lib/tabs.js";
import { parseHash, subOf } from "./src/lib/deepLink.js";
import { BUILTIN_LOOKS, DEFAULT_LOOK } from "./src/lib/lookChoice.js";
import { LOOKS } from "./src/lib/cards/studio.js";
import DATA from "../supabase/functions/semasa-telegram/menu_data.js";
import { CALLBACK_MAX, homeRow, langOf, menuEdit, nodeOf, nodes, pageUrl, readOf, renderMenu, safeSite, tabs } from "../supabase/functions/semasa-telegram/menu.js";
import { commandReply, fastRead } from "../supabase/functions/semasa-telegram/commands.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const ta = async (name, fn) => { try { await fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const RULES = JSON.parse(read("../rules/telegram_menu.json"));
const CASES = JSON.parse(read("../rules/telegram_menu_cases.json"));
const SITE = "https://semasa.example";
const SYSTEM = "system";           // the one group the sidebar does not have: Settings and the bot's own reports
const bm = (a) => a, en = (a, b) => (b == null ? a : b);

t("the webhook's copy of the catalogue is the catalogue, word for word", () => {
  assert.deepEqual(DATA, RULES, "menu_data.js is behind rules/telegram_menu.json: run `python ops/telegram_menu_copy.py`");
});

t("every tab of the page is in the menu, and every page in the menu is a tab", () => {
  const page = tabsOf(bm).map((x) => x.id);
  const held = tabs();
  assert.equal(new Set(held).size, held.length, "a page is in the menu twice");
  assert.deepEqual(page.filter((id) => !held.includes(id)), [], "in src/lib/tabs.js but not in rules/telegram_menu.json: add the page to its segment there");
  assert.deepEqual(held.filter((id) => !page.includes(id)), [], "in rules/telegram_menu.json but no longer a tab: remove it there");
});

t("each page sits in the segment the sidebar puts it in, under the same name in both languages", () => {
  const inBm = Object.fromEntries(tabsOf(bm).map((x) => [x.id, x])), inEn = Object.fromEntries(tabsOf(en).map((x) => [x.id, x]));
  for (const seg of RULES.segments) for (const p of seg.pages) {
    assert.equal(inBm[p.tab].segment || SYSTEM, seg.id, `${p.tab} is in another segment on the page`);
    assert.equal(p.bm, inBm[p.tab].label, `${p.tab}: the Malay name is the page's`);
    assert.equal(p.en, inEn[p.tab].label, `${p.tab}: the English name is the page's`);
  }
});

t("the segments are the sidebar's own, in its order, with the bot's own group last", () => {
  const side = segmentsOf(bm), sideEn = segmentsOf(en);
  const menu = RULES.segments;
  assert.deepEqual(menu.slice(0, -1).map((s) => s.id), side.map((s) => s.id));
  side.forEach((s, i) => {
    assert.equal(menu[i].bm, s.label); assert.equal(menu[i].en, sideEn[i].label);
    assert.deepEqual(menu[i].pages.map((p) => p.tab), s.pages.map((p) => p.id), `${s.id}: the pages in the page's own order`);
  });
  assert.equal(menu.at(-1).id, SYSTEM);
  assert.deepEqual(menu.at(-1).pages.map((p) => p.tab), tabsOf(bm).filter((x) => !x.segment).map((x) => x.id), "Settings, the page with no segment");
});

t("the webhook draws every menu exactly as the worker does, in both languages", () => {
  assert.deepEqual(CASES.cases.map((c) => `${c.node}|${c.lang}`), nodes().flatMap((node) => ["bm", "en"].map((l) => `${node}|${l}`)),
    "rules/telegram_menu_cases.json is behind: run `python ops/telegram_menu_copy.py`");
  for (const c of CASES.cases) {
    const got = renderMenu(c.node, c.lang, CASES.site, CASES.name);
    assert.equal(got.text, c.text, `${c.node} (${c.lang}): the text`);
    assert.deepEqual(got.keyboard.map((row) => row.map((b) => [b.text, b.callback_data ? `cb:${b.callback_data}` : `url:${b.url}`])), c.rows, `${c.node} (${c.lang}): the buttons`);
  }
});

const flat = (node, lang = "bm") => renderMenu(node, lang, SITE, "Wan").keyboard.flat();

t("every menu is reached from home, every button leads somewhere, and none but home is without a way back", () => {
  const all = nodes(), seen = new Set(), todo = ["home"];
  const TAB_IDS = tabsOf(bm).map((x) => x.id);
  while (todo.length) {
    const node = todo.pop();
    if (seen.has(node)) continue;
    seen.add(node);
    const buttons = flat(node);
    if (node !== "home") assert.ok(buttons.some((b) => b.callback_data === "m:home"), `${node} has no way back to the menu`);
    for (const b of buttons) {
      assert.notEqual("callback_data" in b, "url" in b, `${node}: ${b.text} is neither a tap nor a link`);
      if (b.url) {
        assert.ok(b.url.startsWith(SITE + "/"));
        const target = b.url.slice(SITE.length + 1).replace(/^#/, "");
        // the page must open on exactly this address: App.jsx reads it with parseHash
        if (target) assert.equal(parseHash(target, TAB_IDS).tab, target.split("/")[0], `${node}: ${b.text} opens no page (${target})`);
        continue;
      }
      const [kind, ...rest] = b.callback_data.split(":");
      assert.ok(kind === "m" || kind === "a", b.callback_data);
      if (kind === "m" && rest[0] !== "lang") { assert.ok(all.includes(rest.join(":")), `${node}: ${b.text} opens no menu`); todo.push(rest.join(":")); }
    }
  }
  assert.deepEqual([...seen].sort(), [...all].sort(), "a menu no button opens");
  const opened = new Set(all.flatMap((node) => flat(node)).filter((b) => b.url?.includes("#")).map((b) => b.url.split("#")[1].split("/")[0]));
  assert.deepEqual(TAB_IDS.filter((id) => id !== "papan" && !opened.has(id)), [], "a page no button opens");
  assert.ok(flat("home").some((b) => b.url === SITE + "/"), "the dashboard is Open Semasa");
});

t("Telegram's limits: 64 bytes of callback data, two buttons to a row, a menu that fits a phone", () => {
  assert.equal(CALLBACK_MAX, 64);
  const bytes = (s) => new TextEncoder().encode(s).length;
  for (const node of nodes()) for (const lang of ["bm", "en"]) {
    const { text, keyboard } = renderMenu(node, lang, SITE, "W".repeat(40));
    assert.ok(text.length > 0 && text.length <= 1500, `${node}: the text stays short`);
    assert.ok(keyboard.length >= 1 && keyboard.length <= 10, `${node} (${lang}): ${keyboard.length} rows`);
    for (const row of keyboard) {
      assert.ok(row.length >= 1 && row.length <= 2, `${node}: ${row.length} buttons in a row`);
      for (const b of row) {
        assert.ok(b.text.length >= 1 && b.text.length <= 40, `${node}: "${b.text}" is cut on a phone`);
        if (b.callback_data) assert.ok(bytes(b.callback_data) <= CALLBACK_MAX, b.callback_data);
        else assert.ok(b.url.startsWith("https://") && b.url.length < 200);
      }
    }
  }
  assert.ok(renderMenu("home", "bm", SITE).keyboard.length <= 9, "the home menu: quick buttons, segments two to a row, one closing row");
});

t("both languages are there, and no em dash is in anything a person reads", () => {
  const walk = (node, path, out) => {
    if (node && typeof node === "object") for (const [k, v] of Object.entries(node)) walk(v, `${path}.${k}`, out);
    else if (typeof node === "string" && !path.endsWith("._about")) out.push([path, node]);
    return out;
  };
  for (const [path, s] of walk(RULES, "", [])) { assert.ok(s.trim(), path); assert.ok(!/[—–]/.test(s), `${path}: an em dash`); }
  const both = (x, where) => assert.ok(x?.bm?.trim() && x?.en?.trim(), `${where} needs both languages`);
  both(RULES.home.text, "home"); both(RULES.home.open, "open"); both(RULES.home.lang, "lang");
  for (const [k, w] of Object.entries(RULES.words)) both(w, k);
  for (const seg of RULES.segments) {
    both(seg, seg.id);
    for (const p of seg.pages) { both(p, p.tab); both(p.about, `${p.tab} about`); for (const i of p.items || []) both(i, `${p.tab} item`); }
    for (const i of seg.items || []) both(i, `${seg.id} item`);
  }
  assert.equal(renderMenu("home", "en", SITE, "Wan").text.startsWith("Hi Wan"), true);
  assert.equal(langOf("en"), "en"); assert.equal(langOf(undefined), "bm"); assert.equal(langOf("id"), "bm", "Malay unless English was chosen");
});

t("the looks a poster or a carousel button offers are looks the page has, under the page's own names", () => {
  // the page's own names are the picker's (cards/studio.js LOOKS: bm and en)
  for (const kind of ["poster", "carousel", "post_carousel", "post_card"]) for (const k of RULES.looks[kind]) {
    const name = RULES.looks.names[k];
    assert.ok(name, `${k} has no name`);
    if (k === "threads") continue;                    // Threads is the picker's own entry (lib/threadsSlides.js), not one of Studio's looks
    assert.ok(BUILTIN_LOOKS.includes(k), `${k} is not a look`);
    const page = LOOKS.find((l) => l.k === k);
    assert.deepEqual({ bm: name.bm, en: name.en }, { bm: page.bm, en: page.en }, `${k}: the page calls it something else`);
  }
  assert.equal(RULES.looks.post_carousel[0], "journal", "Diari leads the buttons under a draft");
  assert.ok(!RULES.looks.post_card.includes("journal") && !RULES.looks.post_card.includes("threads"), "a single card never offers Diari or Threads");
  assert.equal(RULES.looks.carousel[0], DEFAULT_LOOK);
  assert.equal(RULES.looks.poster.length, 9, "the hand-drawn default and the eight poster looks");
});

t("a link can name a choice inside a page, and the old addresses still mean what they meant", () => {
  const ids = tabsOf(bm).map((x) => x.id);
  assert.deepEqual(parseHash("#design/comic", ids), { tab: "design", sub: "comic" });
  assert.deepEqual(parseHash("design", ids), { tab: "design", sub: "" });
  assert.deepEqual(parseHash("#li-post", ids), { tab: "li-post", sub: "" });
  assert.equal(parseHash("#posts", ids).tab, "", '"#posts" was never a page: the bot linked to it and landed on the dashboard');
  assert.equal(parseHash("#bil/0123456789abcdef0123456789abcdef", ids).tab, "", "a client's paper is not the billing tab");
  assert.equal(parseHash("#crm/unsub/0123456789abcdef0123456789abcdef", ids).tab, "", "nor is the unsubscribe page the CRM tab");
  assert.equal(parseHash("#design/Comic", ids).tab, ""); assert.equal(parseHash("#nothing/x", ids).tab, ""); assert.equal(parseHash("", ids).tab, "");
  assert.equal(subOf("design", "#design/comic"), "comic"); assert.equal(subOf("design", "#design-lib"), ""); assert.equal(subOf("design", "#video/comic"), "");
  // the catalogue's own links to a choice: each opens a real page, and the Design page takes a kind only when it offers it
  const links = RULES.segments.flatMap((s) => s.pages.flatMap((p) => (p.items || []).filter((i) => i.link).map((i) => [p.tab, i.link])));
  assert.ok(links.some(([, l]) => l === "design/comic"), "the comic poster is in the menu as a link, whichever way that page is built");
  for (const [tab, link] of links) assert.equal(parseHash(link, ids).tab, tab, `${link} opens another page than the one it is listed under`);
  const app = read("./src/App.jsx"), design = read("./src/pages/DesignTab.jsx");
  assert.equal((app.match(/parseHash\(h, TAB_IDS\)\.tab \|\| "papan"/g) || []).length, 2, "the first load and every address change read the page the same way");
  assert.match(design, /useSubLink\("design", \(kind\) => \{ if \(designs\.some\(\(d\) => d\[0\] === kind\)\) setDesign\(kind\); \}\);/);
  assert.equal(pageUrl(SITE + "/", "design/comic"), SITE + "/#design/comic"); assert.equal(pageUrl(SITE, "papan"), SITE + "/"); assert.equal(pageUrl(SITE), SITE + "/");
});

// ---- what the webhook answers itself ---------------------------------------------------------------------------------------
const tap = (data, extra = {}) => ({ update_id: 9, callback_query: { id: "cq", from: { id: 111 }, data, message: { message_id: 70, chat: { id: 111, type: "private" }, ...extra } } });
const gate = { owner: true, busy: false, state: {}, site: SITE, name: "Wan" };

t("a tap that opens another menu is redrawn in place by the webhook, in the language chosen", () => {
  const edit = menuEdit(tap("m:s:content"), gate);
  assert.equal(edit.method, "editMessageText"); assert.equal(edit.chat_id, 111); assert.equal(edit.message_id, 70);
  assert.deepEqual(edit.reply_markup.inline_keyboard, renderMenu("s:content", "bm", SITE).keyboard);
  assert.ok(edit.text.startsWith("📰 Kandungan")); assert.ok(!edit.parse_mode);
  assert.ok(menuEdit(tap("m:p:design"), { ...gate, state: { lang: "en" } }).text.startsWith("🎨 Generate poster"));
  assert.ok(menuEdit(tap("m:home"), gate).text.startsWith("Hai Wan"));
  assert.ok(menuEdit(tap("m:s:gone"), gate).text.startsWith("Hai Wan"), "an old button never leads nowhere");
  assert.equal(nodeOf("m:p:li-post"), "p:li-post"); assert.equal(nodeOf("m:lang:en"), null); assert.equal(nodeOf("a:status"), null); assert.equal(nodeOf(undefined), null);
  // under an answer the way back is n:<node>: the same menu as a NEW message, so the answer he just read stays in the chat
  const fresh = menuEdit(tap("n:p:post"), gate);
  assert.equal(fresh.method, "sendMessage"); assert.equal(fresh.message_id, undefined); assert.equal(fresh.chat_id, 111);
  assert.deepEqual(fresh.reply_markup.inline_keyboard, renderMenu("p:post", "bm", SITE).keyboard);
  assert.equal(nodeOf("n:home"), "home"); assert.equal(menuEdit(tap("n:home"), { ...gate, busy: true }), null);
});

t("the worker keeps every tap that changes something, and every tap while something of his is still waiting", () => {
  assert.equal(menuEdit(tap("m:lang:en"), gate), null, "the language is a setting: the worker writes it");
  assert.equal(menuEdit(tap("a:draf"), gate), null, "drafts and their approval are the worker's");
  assert.equal(menuEdit(tap("ok:post-1"), gate), null); assert.equal(menuEdit(tap("c:home"), gate), null);
  assert.equal(menuEdit(tap("m:home"), { ...gate, owner: false }), null);
  assert.equal(menuEdit(tap("m:home"), { ...gate, busy: true }), null, "order is kept: the worker answers what is waiting first");
  assert.equal(menuEdit(tap("m:home"), { ...gate, state: { pending: "cat:idea" } }), null, "a menu button drops a question, and only the worker writes that");
  assert.equal(menuEdit(tap("m:home"), { ...gate, state: null }), null, "an unreadable state is never taken as an empty one");
  assert.equal(menuEdit(tap("m:home"), { ...gate, state: { menu_inline: false } }), null, "the switch that sends every tap to the worker");
  assert.equal(menuEdit(tap("m:home", { chat: { id: -5, type: "supergroup" } }), gate), null);
  assert.equal(menuEdit(tap("m:home"), { ...gate, site: "https://user:pw@x.example" }), null);
  assert.equal(menuEdit({ update_id: 1, message: { text: "m:home" } }, gate), null);
  assert.ok(menuEdit(tap("m:home"), { ...gate, state: { await_note: 5 } }), "a correction waits for his next MESSAGE, not for a tap");
  assert.equal(safeSite("https://x.example/"), true); assert.equal(safeSite("http://x.example"), false); assert.equal(safeSite("https://x.example/?a=1"), false);
});

await ta("a read button is answered by the webhook with the slash command's own text and the way back", async () => {
  for (const act of ["status", "jadual", "kesihatan", "bil", "help"]) assert.equal(readOf(tap(`a:${act}`), gate), act);
  for (const act of ["draf", "draf_r", "idea_l", "poster", "lk:poster:neon", "ralat", "memori", "constructor", "__proto__"]) assert.equal(readOf(tap(`a:${act}`), gate), null, act);
  assert.equal(readOf(tap("a:status"), { ...gate, busy: true }), null); assert.equal(readOf(tap("a:status"), { ...gate, state: { pending: "motion" } }), null);
  assert.equal(readOf(tap("a:status"), { ...gate, owner: false }), null); assert.equal(readOf(tap("m:home"), gate), null);
  const calls = [];
  const db = { from(table) { calls.push(table); const q = { select: () => q, in: () => q, limit: () => q, eq: () => q, maybeSingle: () => q,
    then: (res, rej) => Promise.resolve({ data: [{ kind: "invoice", number: "INV-1", status: "issued", total: 20 }], error: null }).then(res, rej) }; return q; } };
  const reply = await fastRead(db, "bil", { chatId: 111, site: SITE, lang: "en" });
  assert.equal(reply.method, "sendMessage"); assert.match(reply.text, /MYR 20\.00/); assert.deepEqual(calls, ["semasa_billing_docs"]);
  assert.deepEqual(reply.reply_markup.inline_keyboard, [homeRow("en")]); assert.equal(homeRow("en")[0].callback_data, "n:home");
  assert.equal((await fastRead(db, "help", { chatId: 111, site: SITE })).reply_markup.inline_keyboard[0][0].callback_data, "n:home");
  assert.equal(await fastRead(db, "draf", { chatId: 111, site: SITE }), null); assert.equal(await fastRead(db, "menu", { chatId: 111, site: SITE }), null);
  const broken = { from() { const q = { select: () => q, in: () => q, limit: () => q, then: (res, rej) => Promise.resolve({ data: null, error: { message: "x" } }).then(res, rej) }; return q; } };
  assert.equal(await fastRead(broken, "bil", { chatId: 111, site: SITE }), null, "a failed read goes to the worker, never to a zero");
});

t("/menu in the webhook is the same home menu", () => {
  const reply = commandReply("menu", {}, { chatId: 42, site: SITE + "/", username: "Wan", lang: "en" });
  assert.equal(reply.text, renderMenu("home", "en", SITE, "Wan").text);
  assert.deepEqual(reply.reply_markup.inline_keyboard, renderMenu("home", "en", SITE, "Wan").keyboard);
  assert.deepEqual(commandReply("menu", {}, { chatId: 42, site: SITE }).reply_markup.inline_keyboard, renderMenu("home", "bm", SITE).keyboard, "Malay by default");
});

console.log(`telegram menu: ${n} checks ok`);

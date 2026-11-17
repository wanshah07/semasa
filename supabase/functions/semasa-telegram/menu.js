// Semasa on Telegram, the button menu, as the webhook draws it (Wan, 16 Nov 2026: "make sure all features appear in telegram
// semasa button"). The catalogue is rules/telegram_menu.json; menu_data.js is its generated copy (an Edge Function is deployed
// from its own folder and cannot read rules/). The worker draws the same menus (backend/semasa/telegram_menu.py), and
// rules/telegram_menu_cases.json holds what both must draw: web/telegramMenu.test.mjs and backend/tests/test_telegram_menu.py.
//
// Why the webhook draws menus at all: a tap that only opens another menu needs no worker, so it is answered here, at once, by
// redrawing the message (editMessageText in the response body; this function still never holds the bot token). The way back
// under an ANSWER is n:<node>: the same menu as a new message, so the answer stays in the chat. A button that DOES something
// (a:<act>) goes to the worker as before, except the reads commands.js could already answer.
// Nothing here approves, publishes or writes a row.
import DATA from "./menu_data.js";

export const MENU = DATA;
const PER_ROW = 2;
export const CALLBACK_MAX = 64;

export const langOf = (value) => (value === "en" ? "en" : "bm");
const label = (item, lang) => (item.icon ? `${item.icon} ` : "") + String(item[lang]);

/** The page's address for a tab ("post") or a choice inside one ("design/comic"). The dashboard is the bare address. */
export function pageUrl(site, target = "") {
  const base = String(site || "").replace(/\/+$/, "") + "/";
  return target === "" || target === "papan" ? base : `${base}#${target}`;
}

/** Only an https address with no login, query or fragment is ever put on a button. */
export function safeSite(site) {
  try {
    const url = new URL(site);
    return url.protocol === "https:" && !url.username && !url.password && !url.search && !url.hash;
  } catch {
    return false;
  }
}

const rowsOf = (buttons) => {
  const rows = [];
  for (let i = 0; i < buttons.length; i += PER_ROW) rows.push(buttons.slice(i, i + PER_ROW));
  return rows;
};
const itemButton = (item, lang, site) => (item.link
  ? { text: label(item, lang), url: pageUrl(site, item.link) }
  : { text: label(item, lang), callback_data: `a:${item.act}` });
const menuButton = (lang) => ({ text: DATA.words.menu[lang], callback_data: "m:home" });

export const segmentOf = (id) => DATA.segments.find((s) => s.id === id) || null;
export function pageOf(tab) {
  for (const seg of DATA.segments) for (const page of seg.pages) if (page.tab === tab) return [seg, page];
  return null;
}
export const tabs = () => DATA.segments.flatMap((s) => s.pages.map((p) => p.tab));
/** Every menu there is: home, each segment, each page that has its own menu. */
export const nodes = () => ["home", ...DATA.segments.map((s) => `s:${s.id}`),
  ...DATA.segments.flatMap((s) => s.pages.filter((p) => p.items?.length).map((p) => `p:${p.tab}`))];

function home(lang, site, name) {
  const other = lang === "bm" ? "en" : "bm";
  const keyboard = [
    ...rowsOf(DATA.home.quick.map((i) => itemButton(i, lang, site))),
    ...rowsOf(DATA.segments.map((s) => ({ text: label(s, lang), callback_data: `m:s:${s.id}` }))),
    [{ text: DATA.home.lang[lang], callback_data: `m:lang:${other}` }, { text: label(DATA.home.open, lang), url: pageUrl(site) }],
  ];
  return { text: DATA.home.text[lang].replace("{name}", name || "Wan"), keyboard };
}

function segmentMenu(seg, lang, site) {
  const lines = seg.pages.map((p) => `• ${p[lang]}: ${p.about[lang]}`);
  const keyboard = seg.pages.map((p) => [p.items?.length
    ? { text: label(p, lang), callback_data: `m:p:${p.tab}` }
    : { text: label(p, lang), url: pageUrl(site, p.tab) }]);
  keyboard.push(...rowsOf((seg.items || []).map((i) => itemButton(i, lang, site))), [menuButton(lang)]);
  return { text: `${label(seg, lang)}\n\n${lines.join("\n")}\n\n${DATA.words.segment_hint[lang]}`, keyboard };
}

function pageMenu(seg, page, lang, site) {
  const keyboard = page.items.map((i) => [itemButton(i, lang, site)]);
  keyboard.push([{ text: DATA.words.open_page[lang], url: pageUrl(site, page.tab) }],
    [{ text: `⬅ ${seg[lang]}`, callback_data: `m:s:${seg.id}` }, menuButton(lang)]);
  return { text: `${label(page, lang)}\n${page.about[lang]}\n\n${DATA.words.segment_hint[lang]}`, keyboard };
}

/** { text, keyboard } for a menu: "home", "s:<segment>" or "p:<tab>". A name nobody knows is the home menu. */
export function renderMenu(node, lang, site, name = "Wan") {
  const l = langOf(lang);
  const at = String(node || "").indexOf(":");
  const kind = at < 0 ? String(node || "") : String(node).slice(0, at);
  const key = at < 0 ? "" : String(node).slice(at + 1);
  if (kind === "s") {
    const seg = segmentOf(key);
    if (seg) return segmentMenu(seg, l, site);
  }
  if (kind === "p") {
    const found = pageOf(key);
    if (found && found[1].items?.length) return pageMenu(found[0], found[1], l, site);
    if (found) return segmentMenu(found[0], l, site);
  }
  return home(l, site, name);
}

/** The menu a tapped button names ("m:s:content" and "n:s:content" give "s:content"); null for the language switch and
    anything else. */
export function nodeOf(data) {
  if (typeof data !== "string" || !(data.startsWith("m:") || data.startsWith("n:"))) return null;
  const node = data.slice(2);
  return node.startsWith("lang:") ? null : node;
}

/** Under an answer: the way back to the home menu, as a new message (n:), so the answer stays. */
export const homeRow = (lang) => [{ text: DATA.words.menu[langOf(lang)], callback_data: "n:home" }];

/* A tap the webhook may answer itself. The rules are the fast commands' own (commands.js): only the linked account, in its
   private chat, with nothing of his still waiting for the worker (`busy`, and unreadable counts as busy) and no question
   pending. A pending question goes to the worker because a menu button DROPS it, and only the worker writes that row.
   `state.menu_inline === false` sends every tap to the worker: the switch if a Telegram app ever shows the redraw badly. */
function tapEligible(update, { owner, busy, state }) {
  const cq = update?.callback_query;
  if (!cq || !owner || busy || state === null || typeof state !== "object" || Array.isArray(state)) return false;
  if (state.pending || state.menu_inline === false) return false;
  return cq.message?.chat?.type === "private" && cq.message?.chat?.id != null && Number.isInteger(cq.message?.message_id);
}

/** The webhook's own answer to a tap on a menu button, or null to leave the tap to the worker: m:<node> redraws the tapped
    message, n:<node> sends the menu as a new one. */
export function menuEdit(update, { owner, busy = false, state, site, name = "Wan" } = {}) {
  const data = update?.callback_query?.data;
  const node = nodeOf(data);
  if (node == null || !tapEligible(update, { owner, busy, state }) || !safeSite(site)) return null;
  const { text, keyboard } = renderMenu(node, state.lang, site, name);
  const msg = update.callback_query.message;
  const body = { chat_id: msg.chat.id, text, disable_web_page_preview: true, reply_markup: { inline_keyboard: keyboard } };
  return data.startsWith("n:") ? { method: "sendMessage", ...body } : { method: "editMessageText", message_id: msg.message_id, ...body };
}

// the reads a menu button shares with the fast slash commands (commands.js commandReply)
const READS = { status: "status", jadual: "jadual", kesihatan: "kesihatan", bil: "bil", help: "help" };

/** "status" for a tap on a:status and the like, when the webhook may answer it; else null (the worker does). */
export function readOf(update, { owner, busy = false, state } = {}) {
  const data = update?.callback_query?.data;
  if (typeof data !== "string" || !data.startsWith("a:") || !tapEligible(update, { owner, busy, state })) return null;
  const act = data.slice(2);
  return Object.hasOwn(READS, act) ? READS[act] : null;
}

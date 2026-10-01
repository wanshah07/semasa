/* A small Markdown reader for the AI chat (Wan, 1 Oct 2026: answers "almost similar with Claude"). It turns the model's text into a
   TREE of plain objects; components/Markdown.jsx draws the tree as React elements. No HTML is ever passed through: a tag in the text
   is text, so a model (or a page it read) cannot put a script or an element into the chat. Pure, so Node tests it.

   Covered: headings (#, ##, ###), paragraphs, **bold**, *italic*, `code`, fenced code blocks, bullet and numbered lists (one level of
   nesting), > quotes, tables with a |---| row, --- rules, links [text](https://…) and bare https:// addresses (only http(s) and mailto
   ever become links). Anything else is ordinary text. */

const LINK = /^https?:\/\/[^\s<>)\]]+/i;
const SAFE_HREF = /^(https?:\/\/|mailto:)/i;

/** Inline text → [{ t: "text"|"strong"|"em"|"code"|"link"|"br", s?: string, href?: string, c?: [...] }] */
export function inline(src) {
  const out = [];
  let text = "";
  const flush = () => { if (text) { out.push({ t: "text", s: text }); text = ""; } };
  let i = 0;
  const s = String(src ?? "");
  while (i < s.length) {
    const ch = s[i];
    if (ch === "\\" && i + 1 < s.length) { text += s[i + 1]; i += 2; continue; }
    if (ch === "`") {
      const end = s.indexOf("`", i + 1);
      if (end > i) { flush(); out.push({ t: "code", s: s.slice(i + 1, end) }); i = end + 1; continue; }
    }
    if (s.startsWith("**", i)) {
      const end = s.indexOf("**", i + 2);
      if (end > i + 2) { flush(); out.push({ t: "strong", c: inline(s.slice(i + 2, end)) }); i = end + 2; continue; }
    }
    if ((ch === "*" || ch === "_") && s[i + 1] !== " " && s[i + 1] !== ch) {
      const end = s.indexOf(ch, i + 1);
      if (end > i + 1 && (ch === "*" || !/\w/.test(s[end + 1] || "") && !/\w/.test(s[i - 1] || ""))) { flush(); out.push({ t: "em", c: inline(s.slice(i + 1, end)) }); i = end + 1; continue; }
    }
    if (ch === "[") {
      const close = s.indexOf("](", i);
      const end = close > 0 ? s.indexOf(")", close) : -1;
      if (close > i && end > close) {
        const href = s.slice(close + 2, end).trim();
        const label = s.slice(i + 1, close);
        flush();
        if (SAFE_HREF.test(href)) out.push({ t: "link", href, c: inline(label) });
        else out.push({ t: "text", s: label });
        i = end + 1; continue;
      }
    }
    if (ch === "h" && (s.startsWith("http://", i) || s.startsWith("https://", i)) && !/[\w/]/.test(s[i - 1] || "")) {
      const m = s.slice(i).match(LINK);
      if (m) {
        let url = m[0];
        while (/[.,;:!?]$/.test(url)) url = url.slice(0, -1);    // a full stop after a link is prose, not the link
        flush(); out.push({ t: "link", href: url, c: [{ t: "text", s: url }] }); i += url.length; continue;
      }
    }
    if (ch === "\n") { flush(); out.push({ t: "br" }); i++; continue; }
    text += ch; i++;
  }
  flush();
  return out;
}

const cells = (row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const isSep = (row) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(row);

/** Lines of a list (the item lines and their continuation / nested lines) → items, one level of nesting. */
function listItems(lines, ordered) {
  const items = [];
  const re = ordered ? /^(\s*)(\d+)[.)]\s+(.*)$/ : /^(\s*)[-*+]\s+(.*)$/;
  let cur = null;
  for (const l of lines) {
    const m = l.match(re);
    const indent = m ? m[1].length : 99;
    if (m && indent <= 1) { cur = { text: ordered ? m[3] : m[2], sub: [] }; items.push(cur); continue; }
    if (cur) cur.sub.push(l.replace(/^\s{1,4}/, ""));
  }
  return items.map((it) => ({ c: inline(it.text), children: it.sub.length ? blocks(it.sub) : [] }));
}

/** Lines → blocks: [{ t: "h", n, c } | { t: "p", c } | { t: "code", lang, s } | { t: "ul"|"ol", items } | { t: "quote", children } |
    { t: "table", head, rows } | { t: "hr" }] */
export function blocks(lines) {
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    const fence = l.match(/^\s*```\s*(\w+)?\s*$/);
    if (fence) {
      const body = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) body.push(lines[i++]);
      i++;
      out.push({ t: "code", lang: fence[1] || "", s: body.join("\n") });
      continue;
    }
    const h = l.match(/^(#{1,6})\s+(.*)$/);
    if (h) { out.push({ t: "h", n: Math.min(3, h[1].length), c: inline(h[2].replace(/\s+#+$/, "")) }); i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)) { out.push({ t: "hr" }); i++; continue; }
    if (/^\s*>/.test(l)) {
      const q = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      out.push({ t: "quote", children: blocks(q) });
      continue;
    }
    if (l.includes("|") && i + 1 < lines.length && isSep(lines[i + 1])) {
      const head = cells(l);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      out.push({ t: "table", head: head.map(inline), rows: rows.map((r) => r.map(inline)) });
      continue;
    }
    const ul = /^\s{0,1}[-*+]\s+/.test(l), ol = /^\s{0,1}\d+[.)]\s+/.test(l);
    if (ul || ol) {
      const buf = [];
      const re = ul ? /^\s{0,1}[-*+]\s+/ : /^\s{0,1}\d+[.)]\s+/;
      while (i < lines.length && (re.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && buf.length) || (!lines[i].trim() && i + 1 < lines.length && /^\s{2,}\S/.test(lines[i + 1])))) {
        if (lines[i].trim()) buf.push(lines[i]);
        i++;
      }
      out.push({ t: ul ? "ul" : "ol", items: listItems(buf, ol) });
      continue;
    }
    const p = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*```|\s*>|\s{0,1}[-*+]\s+|\s{0,1}\d+[.)]\s+)/.test(lines[i]) && !(lines[i].includes("|") && i + 1 < lines.length && isSep(lines[i + 1]))) p.push(lines[i++]);
    if (p.length) out.push({ t: "p", c: inline(p.join("\n")) });
    else i++;
  }
  return out;
}

export const parseMarkdown = (text) => blocks(String(text ?? "").replace(/\r\n?/g, "\n").split("\n"));

/** The text with no marks at all (for the copy button and for a thread's title). */
export function plainText(nodes) {
  const inl = (c) => (c || []).map((n) => (n.t === "text" || n.t === "code" ? n.s : n.t === "br" ? "\n" : n.t === "link" ? inl(n.c) : inl(n.c))).join("");
  return (nodes || []).map((b) => {
    if (b.t === "p" || b.t === "h") return inl(b.c);
    if (b.t === "code") return b.s;
    if (b.t === "ul" || b.t === "ol") return b.items.map((it, i) => `${b.t === "ol" ? `${i + 1}. ` : "- "}${inl(it.c)}${it.children.length ? "\n  " + plainText(it.children).replace(/\n/g, "\n  ") : ""}`).join("\n");
    if (b.t === "quote") return plainText(b.children);
    if (b.t === "table") return [b.head, ...b.rows].map((r) => r.map(inl).join(" | ")).join("\n");
    return "";
  }).filter(Boolean).join("\n\n");
}

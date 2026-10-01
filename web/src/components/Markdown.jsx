/* The AI's answer, drawn from lib/markdown.js's tree (Wan, 1 Oct 2026). Every node is a React element with text children: no
   dangerouslySetInnerHTML anywhere, so nothing a model writes can become markup. Links open in a new tab with no referrer. */
import { useMemo } from "react";
import { parseMarkdown } from "../lib/markdown";

function Inline({ nodes }) {
  return (nodes || []).map((n, i) => {
    if (n.t === "text") return n.s;
    if (n.t === "br") return <br key={i} />;
    if (n.t === "code") return <code key={i} className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.9em]">{n.s}</code>;
    if (n.t === "strong") return <strong key={i} className="font-semibold"><Inline nodes={n.c} /></strong>;
    if (n.t === "em") return <em key={i}><Inline nodes={n.c} /></em>;
    if (n.t === "link") return <a key={i} href={n.href} target="_blank" rel="noopener noreferrer nofollow" className="text-accent underline decoration-dotted underline-offset-2 [overflow-wrap:anywhere]"><Inline nodes={n.c} /></a>;
    return null;
  });
}

function Block({ b }) {
  if (b.t === "p") return <p className="my-1.5 leading-relaxed [overflow-wrap:anywhere]"><Inline nodes={b.c} /></p>;
  if (b.t === "h") {
    const cls = b.n === 1 ? "mt-3 text-base font-semibold" : b.n === 2 ? "mt-3 text-[15px] font-semibold" : "mt-2 text-sm font-semibold";
    return b.n === 1 ? <h3 className={cls}><Inline nodes={b.c} /></h3> : b.n === 2 ? <h4 className={cls}><Inline nodes={b.c} /></h4> : <h5 className={cls}><Inline nodes={b.c} /></h5>;
  }
  if (b.t === "code") return <pre className="my-2 overflow-x-auto rounded-tile bg-ink px-3 py-2 font-mono text-[12px] leading-relaxed text-bg"><code>{b.s}</code></pre>;
  if (b.t === "ul" || b.t === "ol") {
    const Tag = b.t;
    return <Tag className={`my-1.5 space-y-0.5 pl-5 ${b.t === "ol" ? "list-decimal" : "list-disc"}`}>
      {b.items.map((it, i) => <li key={i} className="[overflow-wrap:anywhere]"><Inline nodes={it.c} />{it.children.map((c, j) => <Block key={j} b={c} />)}</li>)}
    </Tag>;
  }
  if (b.t === "quote") return <blockquote className="my-2 border-l-2 border-accent/60 pl-3 text-muted">{b.children.map((c, i) => <Block key={i} b={c} />)}</blockquote>;
  if (b.t === "hr") return <hr className="my-3 border-line" />;
  if (b.t === "table") return (
    <div className="my-2 overflow-x-auto"><table className="min-w-[50%] border-collapse text-[13px]">
      <thead><tr>{b.head.map((c, i) => <th key={i} className="border-b border-line px-2 py-1 text-left font-semibold"><Inline nodes={c} /></th>)}</tr></thead>
      <tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="border-b border-line/60 px-2 py-1 align-top [overflow-wrap:anywhere]"><Inline nodes={c} /></td>)}</tr>)}</tbody>
    </table></div>);
  return null;
}

export default function Markdown({ text }) {
  const tree = useMemo(() => parseMarkdown(text), [text]);
  return <div className="text-sm">{tree.map((b, i) => <Block key={i} b={b} />)}</div>;
}

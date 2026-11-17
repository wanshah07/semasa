import { useEffect, useRef } from "react";

/* A page address can name a choice inside the page: #design/comic opens Generate poster with the comic kind chosen. The
   Telegram menu links to these (rules/telegram_menu.json, `link`), so a button can open the very thing it names.

   The part before the slash is the page (App.jsx TAB_IDS); the page reads the rest itself (useSubLink) and ignores a choice it
   does not offer, so a link to a choice that is not built yet still opens the right page. #bil/<token> and #crm/unsub/<token>
   are not these: they are a client's paper and the unsubscribe page, read before any tab, and neither fits the pattern below. */
const SUB = /^[a-z][a-z0-9-]{0,23}$/;

/** { tab, sub } for an address: "design/comic" is the design page with "comic"; an address that names no page is { "", "" }. */
export function parseHash(hash, tabIds) {
  const h = String(hash || "").replace(/^#/, "");
  if (tabIds.includes(h)) return { tab: h, sub: "" };
  const at = h.indexOf("/");
  if (at > 0) {
    const tab = h.slice(0, at), sub = h.slice(at + 1);
    if (tabIds.includes(tab) && SUB.test(sub)) return { tab, sub };
  }
  return { tab: "", sub: "" };
}

/** The choice the address names inside `tab` ("" when it names none, or another page). */
export function subOf(tab, hash = typeof window !== "undefined" ? window.location.hash : "") {
  return parseHash(hash, [tab]).sub;
}

/** Calls `onSub(choice)` when the page opens on, or the address changes to, a choice inside `tab`. A choice the page cannot
    take is ignored: the page stays as it was. */
export function useSubLink(tab, onSub) {
  const fn = useRef(onSub);
  fn.current = onSub;
  useEffect(() => {
    const run = () => {
      const sub = subOf(tab);
      if (!sub) return;
      try { fn.current(sub); } catch { /* not a choice this page has */ }
    };
    run();
    window.addEventListener("hashchange", run);
    return () => window.removeEventListener("hashchange", run);
  }, [tab]);
}

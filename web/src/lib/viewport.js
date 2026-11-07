/* The phone's screen as the chat sees it (pages/ChatTab.jsx; Wan uses Semasa as an iPhone home-screen app).

   100vh and 100dvh do not shrink when the iPhone keyboard opens: Safari shrinks only the VISUAL viewport and lets the page pan
   under the layout one, which is how a composer "pinned to the bottom" ends up under the keyboard. `visualViewport` reports the
   part of the page that is actually on screen, so a column sized from it keeps its box above the keyboard and the message list
   keeps scrolling inside it. The bottom tab bar is fixed to the LAYOUT viewport, so with the keyboard up it sits under the keys:
   while the keyboard is open <html> carries data-kb, which hides the bar and zeroes --tabbar-h (index.css). */
import { useEffect, useState } from "react";

/** The visual viewport's height, its offset from the top of the layout viewport, and whether a keyboard is probably open
    (the visual viewport lost more than 120 px against the window: no toolbar change is that big). */
export function useVisualViewport() {
  const read = () => {
    const vv = typeof window !== "undefined" ? window.visualViewport : null;
    const h = vv ? vv.height : (typeof window !== "undefined" ? window.innerHeight : 800);
    const top = vv ? vv.offsetTop : 0;
    const full = typeof window !== "undefined" ? window.innerHeight : h;
    return { height: Math.round(h), top: Math.round(top), keyboard: full - h > 120 };
  };
  const [state, setState] = useState(read);
  useEffect(() => {
    const vv = window.visualViewport;
    const update = () => setState((s) => { const n = read(); return n.height === s.height && n.top === s.top && n.keyboard === s.keyboard ? s : n; });
    update();
    window.addEventListener("resize", update);
    vv?.addEventListener("resize", update);
    vv?.addEventListener("scroll", update);
    return () => { window.removeEventListener("resize", update); vv?.removeEventListener("resize", update); vv?.removeEventListener("scroll", update); };
  }, []);
  return state;
}

/** Marks <html data-kb> while the keyboard is open, so the bottom bar steps aside (index.css). */
export function useKeyboardFlag(keyboard) {
  useEffect(() => {
    const el = document.documentElement;
    if (keyboard) el.setAttribute("data-kb", ""); else el.removeAttribute("data-kb");
    return () => el.removeAttribute("data-kb");
  }, [keyboard]);
}

/** true below Tailwind's `md` (768 px): the chat's panels open as sheets instead of beside the conversation. */
export function useIsPhone(query = "(max-width: 767.98px)") {
  const [phone, setPhone] = useState(() => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false));
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(query);
    const on = () => setPhone(mq.matches);
    on();
    mq.addEventListener ? mq.addEventListener("change", on) : mq.addListener(on);
    return () => { mq.removeEventListener ? mq.removeEventListener("change", on) : mq.removeListener(on); };
  }, [query]);
  return phone;
}

/** A finger rather than a mouse: Enter then means a new line and the Send button sends. */
export const coarsePointer = () => { try { return window.matchMedia("(pointer: coarse)").matches; } catch { return false; } };

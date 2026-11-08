import { Component } from "react";
import { errorLine, homeUrl, isAppCache } from "../lib/errorScreen";
import { tr } from "../lib/i18n";

/* The screen under everything. Without it one render error anywhere unmounts the whole React tree and the page is blank, on the
   phone app too, with nothing to press (Wan, 8 Nov 2026). It sits ABOVE the theme, language and icon providers, so it uses
   nothing they provide: tr() is a plain function, the colours are fixed with the theme's CSS variables as a first choice, and
   the buttons are plain elements. "Clear the app's copy" removes only Semasa's own caches and service worker; it never touches
   the sign-in, which lives in localStorage. */
const box = { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "24px",
  background: "var(--bg, #f6f8fb)", color: "var(--ink, #15171b)", fontFamily: "system-ui, -apple-system, sans-serif" };
const card = { maxWidth: 460, width: "100%", background: "var(--surface, #fff)", border: "1px solid var(--line, #dfe5ec)",
  borderRadius: 18, padding: "24px", boxShadow: "0 8px 30px rgba(0,0,0,.08)" };
const btn = (primary) => ({ display: "block", width: "100%", minHeight: 44, marginTop: 10, borderRadius: 12, fontSize: 15, fontWeight: 600,
  cursor: "pointer", border: primary ? "0" : "1px solid var(--line, #cfd7e0)", background: primary ? "var(--accent, #1d6fd6)" : "transparent",
  color: primary ? "#fff" : "inherit" });

export default class ErrorBoundary extends Component {
  constructor(props) { super(props); this.state = { error: null, busy: false }; }

  static getDerivedStateFromError(error) { return { error }; }

  componentDidCatch(error, info) {
    // the browser's own console keeps the full stack for whoever opens it; the screen shows one line
    console.error("Semasa error screen:", error, info?.componentStack || "");
  }

  reload = () => { window.location.reload(); };

  home = () => { window.location.replace(homeUrl(window.location.href)); };

  clearCopy = async () => {
    this.setState({ busy: true });
    try {
      const regs = (await navigator.serviceWorker?.getRegistrations?.()) || [];
      await Promise.all(regs.map((r) => r.unregister()));
      const names = (await window.caches?.keys?.()) || [];
      await Promise.all(names.filter(isAppCache).map((n) => window.caches.delete(n)));
    } catch { /* nothing cached, or a browser without these: reloading is still right */ }
    window.location.replace(homeUrl(window.location.href));
  };

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={box} role="alert" data-error-screen>
        <div style={card}>
          <h1 style={{ margin: 0, fontSize: 20 }}>{tr("Ada yang tidak kena", "Something went wrong")}</h1>
          <p style={{ margin: "10px 0 0", lineHeight: 1.5, fontSize: 14 }}>
            {tr("Semasa tidak dapat memaparkan halaman ini. Data dan log masuk anda tidak terjejas. Cuba muat semula; jika masih sama, pergi ke Papan atau kosongkan salinan app.",
              "Semasa could not show this page. Your data and sign-in are not affected. Try reloading; if it is the same, go to Papan or clear the app's copy.")}
          </p>
          <p data-error-line style={{ margin: "12px 0 0", padding: "10px 12px", borderRadius: 10, background: "rgba(127,127,127,.12)",
            fontSize: 12, fontFamily: "ui-monospace, monospace", overflowWrap: "anywhere" }}>{errorLine(this.state.error)}</p>
          <button type="button" style={btn(true)} onClick={this.reload}>{tr("Muat semula", "Reload")}</button>
          <button type="button" style={btn(false)} onClick={this.home}>{tr("Pergi ke Papan", "Go to Papan")}</button>
          <button type="button" style={btn(false)} disabled={this.state.busy} onClick={this.clearCopy}>
            {this.state.busy ? tr("Mengosongkan…", "Clearing…") : tr("Kosongkan salinan app dan muat semula", "Clear the app's copy and reload")}</button>
        </div>
      </div>
    );
  }
}

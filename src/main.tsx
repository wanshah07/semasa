import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./theme.css";

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);

// the service worker makes it an installable app (phone, tablet, desktop) and opens offline
if ("serviceWorker" in navigator && location.protocol === "https:") {
  window.addEventListener("load", () => { navigator.serviceWorker.register("./sw.js").catch(() => { /* a plain page still works */ }); });
}

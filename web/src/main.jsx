import React from "react";
import ReactDOM from "react-dom/client";
import { LucideProvider } from "lucide-react";
import App from "./App";
import { ThemeProvider } from "./design/ThemeProvider";
import { LangProvider } from "./lib/i18n";
import "./index.css";
import { ICON_SET } from "./lib/iconSet";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider>
      <LangProvider>
        <LucideProvider {...ICON_SET}>
          <App />
        </LucideProvider>
      </LangProvider>
    </ThemeProvider>
  </React.StrictMode>,
);

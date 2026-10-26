import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { LucideProvider, Plus } from "lucide-react";
import { ICON_SET } from "./src/lib/iconSet.js";
import { readFileSync } from "node:fs";

const html = renderToStaticMarkup(createElement(LucideProvider, ICON_SET, createElement(Plus, { size: 14 })));
assert.match(html, /stroke-width="1.5"/, "the set is drawn at 1.5, not the library's 2");
assert.match(html, /class="[^"]*semasa-icon/, "every icon carries the class that squares its ends");
const own = renderToStaticMarkup(createElement(LucideProvider, ICON_SET, createElement(Plus, { strokeWidth: 2 })));
assert.match(own, /stroke-width="2"/, "an icon that sets its own weight keeps it");
assert.match(readFileSync(new URL("./src/index.css", import.meta.url), "utf8"), /\.semasa-icon\s*\{[^}]*stroke-linecap:\s*square[^}]*stroke-linejoin:\s*miter/);
assert.match(readFileSync(new URL("./src/main.jsx", import.meta.url), "utf8"), /<LucideProvider \{\.\.\.ICON_SET\}>/, "the page is wrapped in the provider");
console.log("icon set ok");

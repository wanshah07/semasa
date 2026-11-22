// Node needs an import attribute for JSON that Vite does not: tests that copy src/lib/compliance.js into a temp folder also copy
// src/lib/glossary.js beside it with rules/glossary.json inlined. `glossarySource()` is that copy's text.
import { readFileSync } from "node:fs";

export function glossarySource() {
  const json = readFileSync(new URL("../rules/glossary.json", import.meta.url), "utf8");
  return readFileSync(new URL("./src/lib/glossary.js", import.meta.url), "utf8").replace(/^import GLOSSARY from .*$/m, `const GLOSSARY = ${json};`);
}

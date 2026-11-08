import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { errorLine, homeUrl, isAppCache } from "./src/lib/errorScreen.js";

// one line, cut, never a token
assert.equal(errorLine(new Error("cannot add `postgres_changes` callbacks\n  for realtime:x after `subscribe()`.")), "cannot add `postgres_changes` callbacks for realtime:x after `subscribe()`.");
assert.equal(errorLine("x".repeat(500)).length, 200); assert.ok(errorLine("x".repeat(500)).endsWith("…"));
assert.equal(errorLine(null), "Unknown error"); assert.equal(errorLine(undefined), "Unknown error"); assert.equal(errorLine({ message: "  " }), "Unknown error");
const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEFghi";
assert.ok(!errorLine(`bad token ${jwt} here`).includes("eyJ")); assert.ok(errorLine(`bad token ${jwt}`).includes("[token]"));
assert.ok(!/abcdef123456789012/.test(errorLine("apikey=abcdef1234567890123 failed")));

// "go to Papan" drops the #segment and keeps the page
assert.equal(homeUrl("https://socialmedia.kkmhalalconsultant.com/#api"), "https://socialmedia.kkmhalalconsultant.com/");
assert.equal(homeUrl("https://x.test/semasa/?a=1#video"), "https://x.test/semasa/?a=1");
assert.equal(homeUrl("not a url"), "not a url");

// only Semasa's own caches are cleared
assert.ok(isAppCache("semasa-shell-5186466447c4") && isAppCache("semasa-assets"));
assert.ok(!isAppCache("workbox-precache") && !isAppCache("") && !isAppCache(undefined));

// the screen is mounted above every provider, so a crash in one of them is caught too
const main = readFileSync(new URL("./src/main.jsx", import.meta.url), "utf8");
assert.ok(main.indexOf("<ErrorBoundary>") < main.indexOf("<ThemeProvider>") && main.indexOf("</ThemeProvider>") < main.indexOf("</ErrorBoundary>"));
// and it never touches the sign-in (localStorage), only caches and the service worker
const comp = readFileSync(new URL("./src/components/ErrorBoundary.jsx", import.meta.url), "utf8");
assert.ok(!/localStorage|sessionStorage|signOut/.test(comp.replace(/\/\*[\s\S]*?\*\//g, "")), "the error screen must not clear the sign-in");
console.log("errorScreen: ok");

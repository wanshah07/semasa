import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { CLIS, CODE_APIS, PY_PACKAGES, buildStack, countByKind, filterStack, itemRow, liveOf, modelsOf } from "./src/lib/stack.js";

const dir = new URL("../.github/workflows/", import.meta.url);
const flows = readdirSync(dir).filter((f) => /\.ya?ml$/.test(f)).map((f) => [f, readFileSync(new URL(f, dir), "utf8")]);
const all = flows.map(([, s]) => s).join("\n");

// every secret a workflow reads is named by one entry, and every name an entry gives is read by some workflow
const used = new Set([...all.matchAll(/secrets\.([A-Z0-9_]+)/g)].map((m) => m[1]));
const named = new Set(CODE_APIS.flatMap((a) => a.env));
for (const s of used) assert.ok(named.has(s), `the workflows read secrets.${s}: add it to an entry in web/src/lib/stack.js CODE_APIS`);
for (const s of named) assert.ok(used.has(s), `CODE_APIS names ${s} but no workflow reads it: remove it or fix the name`);
assert.equal(new Set(CODE_APIS.map((a) => a.id)).size, CODE_APIS.length, "entry ids are unique");

// every CLI listed is run by some workflow
for (const c of CLIS) assert.ok(flows.some(([, s]) => c.find.test(s)), `no workflow runs ${c.name}`);

// the Python SDKs are backend/requirements.txt, line by line
const req = readFileSync(new URL("../backend/requirements.txt", import.meta.url), "utf8").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#"))
  .map((l) => { const m = /^([A-Za-z0-9_.\-\[\]]+)\s*(.*)$/.exec(l); return [m[1], m[2].trim()]; });
assert.deepEqual(PY_PACKAGES, req, "web/src/lib/stack.js PY_PACKAGES must match backend/requirements.txt");

// probe rows: models clean, the configured one first; the state
const gem = { slug: "gemini", name: "Gemini", model: "models/gemini-3.6-flash", key_set: true, reachable: true, chat_ok: false, models: ["models/aqa", "models/gemini-3.6-flash", "models/aqa"] };
assert.deepEqual(modelsOf(gem), ["gemini-3.6-flash", "aqa"]);
assert.deepEqual(modelsOf({ models: [{ id: "x" }, null, 3] }), ["x"], "only names and {id} objects are models");
assert.equal(liveOf(gem), "models"); assert.equal(liveOf({ chat_ok: true }), "up"); assert.equal(liveOf({ key_set: false }), "nokey"); assert.equal(liveOf({}), "down");

const pkg = { dependencies: { react: "^18.3.1", recharts: "~2.12.0" }, devDependencies: { vite: "^5.4.0" } };
const probe = [gem, { slug: "rootsys", name: "rootsys (Afiq)", role: "primary", base_url: "https://rootsys.cloud/v1", model: "glm-5.3", key_set: true, reachable: true, chat_ok: true, models: ["glm-5.3", "deepseek-v4-pro"] }];
const repos = [{ full_name: "wanshah07/semasa", html_url: "https://github.com/wanshah07/semasa", ci: "green", default_branch: "main" }];
const library = [{ id: "l1", full_name: "OpenTalker/SadTalker", html_url: "https://github.com/OpenTalker/SadTalker", category: "motion", summary_bm: "Wajah bercakap" },
  { id: "l2", full_name: "wanshah07/Semasa", url: "https://github.com/wanshah07/semasa" }];
const mine = [{ id: "m1", kind: "api", name: "ElevenLabs", url: "https://elevenlabs.io", models: ["eleven_v3"], env_key: "ELEVENLABS_API_KEY", status: "trial" }];
const rows = buildStack({ pkg, probe, repos, library, mine }, 0);
const by = (k) => rows.find((r) => r.key === k);
assert.deepEqual(by("code:gemini").models, ["gemini-3.6-flash", "aqa"], "the probe's models sit on the Gemini entry");
assert.equal(by("code:gemini").live, "models");
assert.equal(rows.filter((r) => /gemini/i.test(r.name)).length, 1, "Gemini is listed once, not again as a probe row");
assert.equal(by("probe:rootsys").version, "glm-5.3"); assert.deepEqual(by("probe:rootsys").models, ["glm-5.3", "deepseek-v4-pro"]); assert.equal(by("probe:rootsys").live, "up");
assert.equal(by("npm:react").version, "18.3.1"); assert.equal(by("npm:vite").used, "binaan web");
assert.equal(by("py:yt-dlp[default]").url, "https://pypi.org/project/yt-dlp/");
assert.equal(by("office:wanshah07/semasa").live, "up");
assert.ok(by("lib:l1") && !by("lib:l2"), "a library repo that is also an office repo is listed once");
assert.equal(by("mine:m1").env[0], "ELEVENLABS_API_KEY"); assert.equal(by("mine:m1").status, "trial");
assert.equal(by("code:edge-tts").kind, "service"); assert.equal(by("cli:actions").kind, "service");
const n = countByKind(rows);
assert.equal(n.all, rows.length); assert.equal(n.repo, 2); assert.equal(n.cli, CLIS.filter((c) => !c.kind).length);
assert.equal(n.api, CODE_APIS.filter((a) => !a.kind).length + 1 + 1, "code APIs, rootsys from the probe, and Wan's own");
assert.deepEqual(filterStack(rows, "api", "deepseek").map((r) => r.key), ["probe:rootsys"], "a model name finds its gateway");
assert.deepEqual(filterStack(rows, "all", "BUFFER_API_KEY").map((r) => r.key), ["code:buffer"], "a secret's name finds its service");
assert.equal(filterStack(rows, "sdk").length, 3 + PY_PACKAGES.length);
assert.equal(buildStack({}, 1).find((r) => r.key === "code:buffer").used.startsWith("Publishes"), true, "English when asked");

const t = (bm) => bm;
assert.match(itemRow({ kind: "api", name: " " }, t).error, /nama/);
assert.match(itemRow({ kind: "x", name: "A" }, t).error, /jenis/);
assert.match(itemRow({ kind: "api", name: "A", url: "elevenlabs.io" }, t).error, /https/);
assert.match(itemRow({ kind: "api", name: "A", env_key: "sk-proj-abc123" }, t).error, /Jangan tampal kunci/, "a key's value is refused");
const ok = itemRow({ kind: "api", name: " ElevenLabs ", url: "https://elevenlabs.io", env_key: "ELEVENLABS_API_KEY", models: "eleven_v3, eleven_flash\neleven_v3", status: "weird" }, t).row;
assert.deepEqual(ok.models, ["eleven_v3", "eleven_flash"]); assert.equal(ok.name, "ElevenLabs"); assert.equal(ok.status, "active");
console.log("stack.test.mjs: ok");

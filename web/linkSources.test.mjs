// Wan's own websites and LinkedIn lists (src/lib/linkSources.js): what an address is, what is kept of a pasted list, and that
// saving one list leaves the rest of the settings row alone. The address rules mirror backend/semasa/own_links.py.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LINK_SECTIONS, cleanPages, cleanPosts, cleanSites, linkSummary, linkedinKind, linkedinOf, refused, sitesOf, webUrl, withLinkedin, withSites } from "./src/lib/linkSources.js";
import { watchIdea } from "./src/lib/watchIdea.js";

assert.deepEqual(LINK_SECTIONS, ["website", "linkedin"]);
assert.equal(webUrl("https://lom.agc.gov.my/index.php#top"), "https://lom.agc.gov.my/index.php");
assert.equal(webUrl("javascript:void(0)"), ""); assert.equal(webUrl("lom"), ""); assert.equal(webUrl("mailto:a@b.c"), "");
assert.deepEqual(cleanSites("https://lom.agc.gov.my/index.php\nhttps://lom.agc.gov.my/index.php, bukan pautan https://www.npra.gov.my/"),
  ["https://lom.agc.gov.my/index.php", "https://www.npra.gov.my/"]);
assert.equal(cleanSites(Array.from({ length: 20 }, (_, i) => `https://a${i}.example.com/`)).length, 12);

// the same four answers as own_links.linkedin_kind (backend/tests/test_own_links.py)
assert.deepEqual(linkedinKind("https://www.linkedin.com/posts/contoh_halal-activity-7506241313038831617-EKDA/?utm_source=share"),
  ["post", "https://www.linkedin.com/posts/contoh_halal-activity-7506241313038831617-EKDA"]);
assert.deepEqual(linkedinKind("https://my.linkedin.com/company/contoh-sdn-bhd/posts/?feedView=all"), ["page", "https://www.linkedin.com/company/contoh-sdn-bhd/"]);
assert.equal(linkedinKind("https://www.linkedin.com/in/seseorang/")[0], "profile");
assert.equal(linkedinKind("https://www.linkedin.com/feed/update/urn:li:activity:7506241313038831617/")[0], "post");
assert.deepEqual(linkedinKind("https://example.com/posts/x"), ["", ""]);
assert.deepEqual(linkedinKind("https://notlinkedin.com/company/x"), ["", ""]);

const pasted = "https://www.linkedin.com/posts/a_b-activity-1/ https://www.linkedin.com/in/seseorang/ https://www.linkedin.com/company/contoh/ apa-apa";
assert.deepEqual(cleanPosts(pasted), ["https://www.linkedin.com/posts/a_b-activity-1"]);
assert.deepEqual(cleanPages(pasted), ["https://www.linkedin.com/company/contoh/"]);
assert.deepEqual(refused(pasted, "post"), { profiles: 1, other: 2 }, "a profile is told apart from a link that is simply the wrong kind");

// saving one list keeps the others and the sweep's report
const row = { enabled: true, last_run: "2026-11-16T09:10:00Z", report: { community: { ok: true } }, community: { threads: { queries: ["halal"] } },
  linkedin: { days: 14, posts: ["https://www.linkedin.com/posts/a_b-activity-1"] } };
const a = withSites(row, ["https://lom.agc.gov.my/index.php", "x"]);
assert.deepEqual(sitesOf(a), ["https://lom.agc.gov.my/index.php"]);
assert.deepEqual([a.report, a.community, a.linkedin, a.last_run], [row.report, row.community, row.linkedin, row.last_run]);
const b = withLinkedin(a, { posts: ["https://www.linkedin.com/posts/c_d-activity-2/"], pages: ["https://www.linkedin.com/company/contoh/posts/"], min_reactions: "120" });
assert.deepEqual(linkedinOf(b), { posts: ["https://www.linkedin.com/posts/c_d-activity-2"], pages: ["https://www.linkedin.com/company/contoh/"], min_reactions: 120, days: 14 });
assert.deepEqual(sitesOf(b), ["https://lom.agc.gov.my/index.php"]);
assert.deepEqual(linkedinOf({}), { posts: [], pages: [], min_reactions: 50, days: 30 });

// the sweep's report for each list
const s = { last_run: "2026-11-16T09:10:00Z", report: { websites: { ok: true, new: 3, shown: 1, at: "2026-11-16T09:11:00Z", errors: { "https://www.dead.example/x": "OSError: no answer" } },
  linkedin: { ok: true, new: 2, shown: 2, profiles_skipped: 1 } } };
const w = linkSummary("website", s);
assert.deepEqual([w.new, w.shown, w.last, w.failing.length, w.failing[0].name], [3, 1, "2026-11-16T09:11:00Z", 1, "dead.example/x"]);
assert.equal(linkSummary("linkedin", s).failing[0].name, "LinkedIn");
assert.deepEqual(linkSummary("website", {}), { new: 0, shown: 0, failing: [], last: undefined });

// an item from either list becomes a LinkedIn idea, and a LinkedIn post is a lead, never a source to name
const idea = watchIdea({ id: "1", section: "linkedin", title: "T", url: "https://www.linkedin.com/posts/a_b-activity-1", source: "LinkedIn · Contoh", summary: "Ringkasan.", raw: { metrics: "182 reactions", original: "Teks asal." } }, {});
assert.equal(idea.stream, "linkedin");
assert.match(idea.summary, /182 reactions/); assert.match(idea.summary, /jangan sebut/i);
assert.equal(watchIdea({ id: "2", section: "website", title: "P.U. (A) 392/2026", url: "https://lom.agc.gov.my/x", source: "Malaysia Federal Legislation", summary: "S." }, {}).stream, "linkedin");
assert.equal(watchIdea({ id: "3", section: "regulatory", title: "T", url: "https://npra.gov.my/x", source: "NPRA" }, {}).stream, "regulab", "a regulator's notice still goes to ws.regulab");

// the page is in the LinkedIn segment, and the two sections are treated as Wan's own in the list
const tabs = readFileSync(new URL("./src/lib/tabs.js", import.meta.url), "utf8");
assert.match(tabs, /id: "li-sumber"[^}]*segment: "linkedin"/);
const app = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
assert.match(app, /"li-sumber"/); assert.match(app, /tab === "li-sumber"/);
console.log("linkSources: ok");

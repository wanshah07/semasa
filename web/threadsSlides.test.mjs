import assert from "node:assert/strict";
import { THREADS, THREADS_LOOK, isThreads, jobDesign, threadsProblems, threadsSample } from "./src/lib/threadsSlides.js";

const pages = threadsSample("regulab");
assert.equal(THREADS_LOOK.k, "threads");
assert.equal(isThreads("threads"), true);
assert.equal(jobDesign("threads", "carousel"), "threads");
assert.equal(jobDesign("grid", "carousel"), "carousel");
assert.equal(threadsProblems(pages).length, 0);
assert.equal(threadsProblems(pages.slice(0, 1))[0].n, 0);
assert.equal(threadsProblems(Array.from({ length: THREADS.maxPages + 1 }, (_, i) => ({ title: `P${i}`, points: [] })))[0].n, 0);
assert.match(threadsProblems([{ title: "", points: [] }, pages[1]])[0].bm, /Halaman 1/);
console.log("threads slides: 8 assertions passed");

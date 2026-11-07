import assert from "node:assert/strict";
import { MAX_PRODUCTS, TEMPLATES, libraryPictures, productOf, productsRefusal, templateLabel, templateOf, templateRow } from "./src/lib/motionTemplates.js";
import { motionRow } from "./src/lib/motion.js";

// three choices: the explainer Motion always made, and the two templates (Wan, 7 Nov 2026)
assert.deepEqual(TEMPLATES.map((x) => x.id), ["explainer", "showcase", "story"]);
for (const x of TEMPLATES) assert.ok(x.bm && x.en && x.descBm && x.descEn, `${x.id} is described in both languages`);
assert.equal(templateOf("story"), "story"); assert.equal(templateOf("nope"), "explainer"); assert.equal(templateOf(undefined), "explainer");

// an explainer row is exactly what motionRow made before: no template key creeps into its options
assert.deepEqual(templateRow({ brief: "PFAS", template: "explainer" }, "u1"), motionRow({ brief: "PFAS" }, "u1"));

// a photo story needs only the idea, and is silent, upright and Malay or English
const story = templateRow({ template: "story", brief: " Malaysia ", language: "both", voice: "male", resolution: "square" }, "u1").row;
assert.equal(story.options.template, "story");
assert.equal(story.voice, "off"); assert.equal(story.resolution, "portrait"); assert.equal(story.language, "bm");
assert.equal(story.brief, "Malaysia"); assert.equal(story.status, "pending"); assert.equal(story.ai_background, false);
assert.equal(story.options.products, undefined, "a story carries no products");
assert.deepEqual(templateRow({ template: "story" }), { error: "empty" });
assert.equal(templateRow({ template: "story", brief: "x", language: "en" }).row.language, "en");

// a showcase needs 1 to 5 products, each with its own picture
assert.deepEqual(templateRow({ template: "showcase", brief: "x", products: [] }), { error: "products:none" });
assert.deepEqual(templateRow({ template: "showcase", brief: "x", products: [{ name: "A" }] }), { error: "products:picture" });
assert.deepEqual(templateRow({ template: "showcase", brief: "x", products: Array(MAX_PRODUCTS + 1).fill({ media_id: "m" }) }), { error: "products:many" });
assert.equal(productsRefusal([{ media_id: "m1" }, { ref: { path: "u/p.png" } }]), "");

const show = templateRow({ template: "showcase", businessId: "valorith", tagline: "  Wangian   harian ",
  products: [{ media_id: "m1", name: " Botol  Satu ", benefits: "Ringan", thumb: "https://x/t.jpg" },
    { ref: { path: "u1/a.png", mime: "image/png", size: 10, rights: "self-owned", source: "", attribution: "" } }] }, "u1").row;
assert.equal(show.brief, "Botol Satu", "with no brief the product names stand in for it");
assert.deepEqual(show.options.products, [{ name: "Botol Satu", benefits: "Ringan", media_id: "m1" },
  { name: "", benefits: "", ref: { path: "u1/a.png", mime: "image/png", size: 10, rights: "self-owned", role: "product" } }]);
assert.deepEqual(show.options.brand, { business_id: "valorith", tagline: "Wangian harian" });
assert.ok(!JSON.stringify(show).includes("https://x/t.jpg"), "the form's thumbnail address is never saved on the row");
assert.equal(templateRow({ template: "showcase", products: [{ media_id: "m" }] }).row.options.brand.business_id, "wsregulab");

// a product keeps only what the worker reads
assert.deepEqual(productOf({ media_id: "m", name: "x".repeat(80), url: "https://evil" }), { name: "x".repeat(60), benefits: "", media_id: "m" });

// the library offers finished pictures only, never a carousel's slides or a video
const lib = libraryPictures([{ id: "a", status: "done", type: "image", generated_media_url: "https://a" },
  { id: "b", status: "pending", type: "image", generated_media_url: "https://b" }, { id: "c", status: "done", type: "video", generated_media_url: "https://c" },
  { id: "d", status: "done", type: "image", mode: "slides", generated_media_url: "https://d" }, { id: "e", status: "done", type: "image" }]);
assert.deepEqual(lib.map((x) => x.id), ["a"]);

assert.equal(templateLabel({ options: { template: "story" } }, 1), "Photo story");
assert.equal(templateLabel({ options: { template: "showcase" } }, 0), "Pameran produk");
assert.equal(templateLabel({ options: {} }), "");

console.log("motionTemplates.test.mjs: ok");

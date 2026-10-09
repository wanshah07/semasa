import assert from "node:assert/strict";
import { colLetter, num, sheetIdOf, tabRange, toObjects, toRow } from "./src/lib/sheet.js";
let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
t("columns and ranges", () => {
  assert.equal(colLetter(1), "A"); assert.equal(colLetter(26), "Z"); assert.equal(colLetter(27), "AA"); assert.equal(colLetter(52), "AZ");
  assert.equal(tabRange("Sheet1"), "Sheet1!A1:Z"); assert.equal(tabRange("My Tab", 3), "'My Tab'!A1:C"); assert.equal(tabRange("It's", 1), "'It''s'!A1:A");
});
t("values to objects and back", () => {
  const o = toObjects([["Name", "Score", ""], ["Ben", "10"], ["Al", "7", "x"]]);
  assert.deepEqual(o.headers, ["Name", "Score", "C"]);
  assert.deepEqual(o.rows, [{ __row: 2, Name: "Ben", Score: "10", C: "" }, { __row: 3, Name: "Al", Score: "7", C: "x" }]);
  assert.deepEqual(toRow(o.headers, { Name: "Cy", Score: 3 }), ["Cy", "3", ""]);
  assert.deepEqual(toObjects([]), { headers: [], rows: [] });
});
t("sheet id and numbers", () => {
  assert.equal(sheetIdOf("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit#gid=0"), "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789");
  assert.equal(sheetIdOf("1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"), "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789");
  assert.equal(sheetIdOf("nonsense"), "");
  assert.equal(num("RM 1,200.50"), 1200.5); assert.equal(num(3), 3); assert.equal(num("—"), null);
});
console.log(`sheet: ${n} checks passed`);

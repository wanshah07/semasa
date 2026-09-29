/* web/src/lib/publishing.js must read the switch exactly as backend/semasa/publisher.py publishing_on does. */
import assert from "node:assert/strict";
import { opensAt, publishingOn } from "./src/lib/publishing.js";

const FROM = "2026-10-02T12:00:00Z";                       // Fri 2 Oct, 20:00 MYT (supabase/023)
const before = Date.parse("2026-10-02T11:59:00Z"), after = Date.parse("2026-10-02T12:00:00Z");
let n = 0;
const t = (name, fn) => { fn(); n++; };

t("off by default", () => assert.equal(publishingOn({}, after), false));
t("enabled is on", () => assert.equal(publishingOn({ enabled: true }, before), true));
t("opens by itself at enabled_from, not a minute before", () => {
  assert.equal(publishingOn({ enabled: false, enabled_from: FROM }, before), false);
  assert.equal(publishingOn({ enabled: false, enabled_from: FROM }, after), true);
});
t("paused wins over both", () => {
  assert.equal(publishingOn({ enabled: true, paused: true }, after), false);
  assert.equal(publishingOn({ enabled_from: FROM, paused: true }, after), false);
});
t("a moment with no zone never opens", () => assert.equal(opensAt({ enabled_from: "2026-10-02T20:00:00" }), null));
t("an offset zone reads", () => assert.equal(opensAt({ enabled_from: "2026-10-02T20:00:00+08:00" }), after));
console.log(`${n}/${n} publishing switch tests pass`);

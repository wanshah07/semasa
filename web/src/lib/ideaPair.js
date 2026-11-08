/* One idea for both streams (Wan, 8 Nov 2026: option 1 — "one idea makes a ws.regulab post in BM and a LinkedIn post in English").
   The two voices are never mixed (CLAUDE.md), so this is NOT one post sent to both: it is TWO ideas, one per stream, each written
   by the worker in its own voice, drawn at its own size (4:5 pictures, 9:16 / 1:1 films) and queued on its own stream's slots.
   Nothing here is shared between the two streams except what Wan typed about the issue (title, link, note, references, media).
   The domain only goes to ws.regulab and the angle only to LinkedIn; a requested slot only to the stream it was asked for.
   Pure functions with no imports, so web/ideaPair.test.mjs runs this under Node as it is. */

export const BOTH = "both";
export const STREAM_CHOICES = [["regulab", "ws.regulab (FB · IG · Threads)"], ["linkedin", "LinkedIn (Wan)"]];

/** The composer's "For" options: the two streams, and both. */
export const streamOptions = (bothLabel) => [...STREAM_CHOICES, [BOTH, bothLabel]];

export const streamsOf = (choice) => (choice === BOTH ? ["regulab", "linkedin"] : [choice === "linkedin" ? "linkedin" : "regulab"]);

/** The idea rows for one choice. `common` is everything the stream does not change; `brief` is the shared brief (look, hook style,
    writing style, format); `position` is `{stream, date, slot}` from an empty slot in the Schedule. With both, each row carries
    `brief.pair` (one id for the two) and `brief.pair_stream` (the other stream), so the Ideas list can show they belong together. */
export function ideaRows(common, { choice, domain = "", angle = "", brief = {}, position = null, pairId = "" } = {}) {
  const streams = streamsOf(choice);
  return streams.map((stream) => {
    const b = { ...brief };
    if (position?.date && position?.slot && position.stream === stream) b.position = { date: position.date, slot: position.slot };
    if (streams.length > 1) { b.pair = pairId; b.pair_stream = streams.find((s) => s !== stream); }
    const row = { ...common, stream, domain: stream === "regulab" ? domain || null : null, angle: stream === "linkedin" ? angle || null : null };
    if (Object.keys(b).length) row.brief = b;
    return row;
  });
}

/** The other half of a pair, found among the ideas shown (same `brief.pair`, the other stream); null when it is not loaded. */
export function pairedIdea(idea, ideas) {
  const id = idea?.brief?.pair;
  if (!id) return null;
  return (ideas || []).find((r) => r.id !== idea.id && r.brief?.pair === id) || null;
}

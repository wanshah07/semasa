/* Browser half of backend/semasa/publishing.py: approval binds the exact content,
 * media identities, provider, channel account ids and MYT schedule. */
const bytes = new TextEncoder();
const hex = (buffer) => [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
const sha = async (value) => hex(await crypto.subtle.digest("SHA-256", bytes.encode(JSON.stringify(value))));

export function providerFor(post, settings) {
  if (["postiz", "buffer", "composio"].includes(post.provider)) return post.provider;
  return settings.publishing?.default_provider === "postiz" && settings.channels?.postiz?.enabled === true
    ? "postiz" : post.stream === "linkedin" ? "composio" : "buffer";
}

export function mediaIdentity(row) {
  return { id: row.id, url: row.generated_media_url, type: row.type,
    mime: row.meta?.mime || (row.type === "video" ? "video/mp4" : "image/jpeg"),
    sha256: row.meta?.sha256, bytes: row.meta?.bytes, seconds: row.meta?.seconds, slide_urls: row.meta?.slide_urls || [] };
}

export async function approvalToken(post, media, accounts) {
  const channels = post.channels || (post.stream === "linkedin" ? ["linkedin"] : []);
  const material = { post_id: post.id, provider: post.provider, stream: post.stream,
    content_sha256: await sha({ text: post.text, lang: post.lang, citation: post.citation }),
    media_sha256: await sha(media.map(mediaIdentity)), channels,
    scheduled_at: post.date && post.slot ? `${post.date}T${post.slot}:00+08:00` : null,
    timezone: "Asia/Kuala_Lumpur", account_ids: Object.fromEntries(channels.map((c) => [c, accounts[c]])) };
  // Python json.dumps inserts spaces; remove only the separators outside JSON strings.
  const compact = JSON.stringify(material).replace(/("(?:\\.|[^"\\])*")|[,:]/g, (m, quoted) => quoted || "");
  return hex(await crypto.subtle.digest("SHA-256", bytes.encode(compact)));
}

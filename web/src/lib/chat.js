/* The AI chat's one door to a model (pages/ChatTab.jsx). Blank on purpose (Wan, 29 Sep 2026: "later then I will
   connect with API, just blank structure").

   To connect it, replace the body of `askAI` and nothing else: the page already sends the whole conversation, the
   attached files and the three switches, and shows whatever `text` comes back. Keep the key OUT of the browser: the
   page is public on GitHub Pages and anything under VITE_* is readable by every visitor, so the call belongs in a
   Supabase Edge Function (or the Cloudflare worker Semasa already has), which holds the key and answers this page.

   messages: [{ role: "user" | "assistant", text: string, at: ISO string }]
   returns   { text: string, connected: boolean } */
export async function askAI(messages, { files = [], settings = {} } = {}) {
  void messages; void files; void settings;
  return { connected: false, text: "" };
}

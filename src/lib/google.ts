/* Google sign-in and the two APIs Bernard uses, in his OWN account: Google Identity Services gives the page a short-lived
   access token in the browser (no server, no secret), and the page calls Drive and Sheets with it. The OAuth client id
   is public by design; it is read from the Settings page (localStorage) or VITE_GOOGLE_CLIENT_ID at build time. */
import { tabRange, toObjects } from "./sheet.js";

export const SCOPES = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets"].join(" ");
const KEY_CLIENT = "bernard.google.client_id";
const KEY_TOKEN = "bernard.google.token";

declare global { interface Window { google?: any } }

export type Token = { access_token: string; expires_at: number; email?: string; name?: string; picture?: string };
export type DriveFile = { id: string; name: string; mimeType: string; modifiedTime?: string; webViewLink?: string; iconLink?: string; size?: string };

export function clientId(): string {
  try { return localStorage.getItem(KEY_CLIENT) || (import.meta as any).env?.VITE_GOOGLE_CLIENT_ID || ""; } catch { return ""; }
}
export function setClientId(id: string) { try { localStorage.setItem(KEY_CLIENT, id.trim()); } catch { /* private window */ } }

export function savedToken(): Token | null {
  try {
    const t = JSON.parse(sessionStorage.getItem(KEY_TOKEN) || "null") as Token | null;
    return t && t.expires_at > Date.now() + 30_000 ? t : null;
  } catch { return null; }
}
export function forget() { try { sessionStorage.removeItem(KEY_TOKEN); } catch { /* ignore */ } }

let gisReady: Promise<void> | null = null;
export function loadGis(): Promise<void> {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  if (gisReady) return gisReady;
  gisReady = new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client"; s.async = true; s.defer = true;
    s.onload = () => res(); s.onerror = () => rej(new Error("Google's sign-in script did not load (offline, or blocked)."));
    document.head.appendChild(s);
  });
  return gisReady;
}

/** Ask Google for a token (opens the account chooser the first time, silent after that while the session lasts). */
export async function signIn(): Promise<Token> {
  const id = clientId();
  if (!id) throw new Error("No Google client id yet: paste it under Settings (see the README for the 5-minute setup).");
  await loadGis();
  const token = await new Promise<Token>((res, rej) => {
    const client = window.google.accounts.oauth2.initTokenClient({
      client_id: id, scope: SCOPES,
      callback: (r: any) => {
        if (r?.error) return rej(new Error(`Google refused: ${r.error}${r.error_description ? ` (${r.error_description})` : ""}`));
        res({ access_token: r.access_token, expires_at: Date.now() + (Number(r.expires_in) || 3600) * 1000 });
      },
      error_callback: (e: any) => rej(new Error(e?.type === "popup_closed" ? "The sign-in window was closed." : `Sign-in failed: ${e?.type || "unknown"}`)),
    });
    client.requestAccessToken({ prompt: savedToken() ? "" : "select_account" });
  });
  try {
    const me = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", { headers: { Authorization: `Bearer ${token.access_token}` } }).then((r) => r.json());
    token.email = me.email; token.name = me.name; token.picture = me.picture;
  } catch { /* the token still works without the name */ }
  try { sessionStorage.setItem(KEY_TOKEN, JSON.stringify(token)); } catch { /* ignore */ }
  return token;
}

export function signOut(token: Token | null) {
  if (token && window.google?.accounts?.oauth2) try { window.google.accounts.oauth2.revoke(token.access_token, () => {}); } catch { /* ignore */ }
  forget();
}

async function api<T>(token: Token, url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, { ...init, headers: { Authorization: `Bearer ${token.access_token}`, "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (r.status === 401) { forget(); throw new Error("Google signed you out (the hour is up). Press Connect again."); }
  if (!r.ok) {
    let msg = `${r.status}`;
    try { const j = await r.json(); msg = j?.error?.message || msg; } catch { /* keep the status */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

/** Recent files, or a name search, in Bernard's Drive (read only). */
export async function listFiles(token: Token, q = "", pageSize = 40): Promise<DriveFile[]> {
  const query = [`trashed = false`, q ? `name contains '${q.replace(/'/g, "\\'")}'` : ""].filter(Boolean).join(" and ");
  const url = `https://www.googleapis.com/drive/v3/files?${new URLSearchParams({ q: query, pageSize: String(pageSize), orderBy: "modifiedTime desc",
    fields: "files(id,name,mimeType,modifiedTime,webViewLink,iconLink,size)" })}`;
  const j = await api<{ files: DriveFile[] }>(token, url);
  return j.files || [];
}

/** The tabs of a spreadsheet. */
export async function sheetTabs(token: Token, spreadsheetId: string): Promise<{ title: string; tabs: string[] }> {
  const j = await api<any>(token, `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}?fields=properties.title,sheets.properties.title`);
  return { title: j?.properties?.title || "", tabs: (j?.sheets || []).map((s: any) => s.properties?.title).filter(Boolean) };
}

/** A tab as objects keyed by its header row. */
export async function readTab(token: Token, spreadsheetId: string, tab: string) {
  const range = encodeURIComponent(tabRange(tab, 40));
  const j = await api<{ values?: string[][] }>(token, `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${range}`);
  return toObjects(j.values || []);
}

/** Append one row under the header. */
export async function appendRow(token: Token, spreadsheetId: string, tab: string, values: string[]) {
  const range = encodeURIComponent(tabRange(tab, 40));
  return api<any>(token, `https://sheets.googleapis.com/v4/spreadsheets/${spreadsheetId}/values/${range}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS`,
    { method: "POST", body: JSON.stringify({ values: [values] }) });
}

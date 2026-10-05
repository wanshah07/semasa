/* My designs in the page (Wan, 4 Oct 2026). A design is a saved look with no words (see backend/semasa/my_designs.py for the
   whole story); the list lives in semasa_settings.designs and is offered through one context, so the look picker, the post
   editor, the idea composer and the Design tab all read the same list without passing it down. A look value is a plain look
   ("classic", "grid", "era", "photo") or "d:<id>" for a design. Pure helpers here; App.jsx supplies the context value. */
import { createContext, useContext } from "react";
import { normDesign } from "./cards/studio.js";

export const DesignsContext = createContext({ designs: [], defaultId: "", ready: false, saveDesigns: null, setDefault: null });
export const useDesigns = () => useContext(DesignsContext);

const TOKEN = /^d:([a-z0-9_]{4,24})$/;
export const designToken = (id) => `d:${id}`;
export const tokenId = (v) => (TOKEN.exec(String(v || "")) || [])[1] || "";
export const newDesignId = () => `x${Math.random().toString(36).slice(2, 8)}`;

/* The address of a design's reference picture (a file in the reference bucket) is the page's business; App.jsx supplies it, so this
   file stays free of the Supabase client and Node can test it. */
let artUrlOf = () => "";
export const setArtResolver = (f) => { artUrlOf = typeof f === "function" ? f : () => ""; };
/** A stored design with its reference picture's address filled in, for drawing in this page (an address already there is kept). */
export const withArt = (pack) => (pack && pack.refart && pack.refart.path && !pack.refart.url ? { ...pack, refart: { ...pack.refart, url: artUrlOf(pack.refart.path) } } : pack);

/** The keys a job carries (the same list as my_designs.KEYS): strings only, so a snapshot is plain data. */
export const DESIGN_KEYS = ["look", "cover", "middle", "closing", "single", "accent", "paper", "bg", "scrim", "mascot", "eyebrow"];
export function packDesign(d) {
  if (!d || !["grid", "era", "photo"].includes(d.look)) return null;
  const out = Object.fromEntries(DESIGN_KEYS.filter((k) => typeof d[k] === "string" && d[k].trim()).map((k) => [k, d[k].trim().slice(0, 120)]));
  if (d.layouts && typeof d.layouts === "object" && Object.keys(d.layouts).length) out.layouts = d.layouts;   // a design made from a reference
  if (d.refart && typeof d.refart === "object" && (d.refart.path || d.refart.url)) out.refart = d.refart;       // ... drawn on its reference picture
  return out;
}

/** A look value -> the family to draw in, the design (normalised, for the renderer) and the snapshot a job carries.
    "d:<id>" naming a design that is gone resolves to Semasa's own drawing, never an error. */
export function resolveLook(value, designs = []) {
  const id = tokenId(value);
  if (!id) return { look: value || "classic", design: null, pack: null, id: "" };
  const found = designs.find((d) => d.id === id);
  const pack = packDesign(found);
  return pack ? { look: pack.look, design: normDesign(withArt(pack)), pack, id } : { look: "classic", design: null, pack: null, id: "" };
}

/** The look value for a job's meta: a design's id when it used one that still exists, else its plain look. */
export const lookValueOf = (meta, designs = []) => (meta?.design_id && designs.some((d) => d.id === meta.design_id)
  ? designToken(meta.design_id) : (meta?.look || "classic"));

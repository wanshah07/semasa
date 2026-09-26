import { useCallback, useEffect, useRef, useState } from "react";
import { Canvas, Circle, FabricImage, Gradient, Group, Line, Point, Rect, Shadow, Textbox, Triangle } from "fabric";
import { AlignCenterHorizontal, AlignCenterVertical, ArrowDown, ArrowLeft, ArrowUp, Bold, Circle as CircleIcon, Copy,
  Download, Eye, EyeOff, ImagePlus, Italic, Layers, Loader2, Lock, Maximize2, Minus, Plus, Redo2, Save, Square,
  Trash2, Triangle as TriangleIcon, Type, Undo2, Unlock } from "lucide-react";
import { FONTS } from "../lib/canvasSeed";
import { timeAgo } from "../lib/format";
import { useLang } from "../lib/i18n";
import { sizeLabel, sizeOf } from "../lib/sizes";
import { refusal, uploadReference } from "../lib/storage";
import { BUCKETS, TABLES, errText, supabase } from "../lib/SupabaseClient";
import SizePicker from "../components/SizePicker";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label } from "../components/ui/Field";

/* Kanvas: a Canva-like editor inside Semasa (Wan, 26 Sep 2026: "add any repo that the design can similar like canva").
   Built on Fabric.js (MIT, github.com/fabricjs/fabric.js), the canvas engine the open-source Canva clones use. It needs
   no server: a design is Fabric JSON in semasa_canvas (supabase/015_canvas.sql), its pictures are addresses in the
   uploads bucket, and its finished PNG is kept beside them. Fabric 7 anchors every object at its CENTRE. */

const PROPS = ["name", "role", "selectable", "evented", "lockMovementX", "lockMovementY", "lockScalingX", "lockScalingY",
  "lockRotation", "hasControls"];
const HISTORY_MAX = 60;
const SNAP_PX = 8;                         // screen pixels: a centre this close to the card's centre line snaps to it
const TEXT_SHADOW = () => new Shadow({ color: "rgba(0,0,0,0.35)", blur: 14, offsetX: 0, offsetY: 3 });
const fontsHref = (f) => `${import.meta.env.BASE_URL}cards/${f}`;

function loadFonts() {
  for (const f of ["fonts.css", "fragrance-fonts.css"]) {
    if (!document.querySelector(`link[data-kanvas="${f}"]`)) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = fontsHref(f); l.dataset.kanvas = f;
      document.head.appendChild(l);
    }
  }
  const wanted = Object.entries(FONTS).flatMap(([fam, ws]) => ws.map((w) => `${w} 40px "${fam}"`));
  return Promise.all(wanted.map((f) => document.fonts.load(f).catch(() => null)));
}

const nearestWeight = (family, want) => {
  const ws = FONTS[family] || [400];
  return ws.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a), ws[0]);
};

export default function CanvasTab({ user, onToast, seed, clearSeed }) {
  const { t } = useLang();
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);          // { row } | { seed } | { blank: sizeId }
  const [newSize, setNewSize] = useState("ig_post_45");

  const load = useCallback(async () => {
    const { data, error: e } = await supabase.from(TABLES.canvas)
      .select("id,name,width,height,size_id,preview_url,updated_at,created_by,source").order("updated_at", { ascending: false }).limit(200);
    if (e) setError(/semasa_canvas/.test(errText(e))
      ? t("Kanvas belum disediakan: jalankan supabase/015_canvas.sql sekali.", "Kanvas is not set up yet: run supabase/015_canvas.sql once.")
      : errText(e));
    else { setError(""); setRows(data || []); }
  }, [t]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (seed) { setOpen({ seed }); clearSeed?.(); } }, [seed, clearSeed]);

  async function openRow(id) {
    const { data, error: e } = await supabase.from(TABLES.canvas).select("*").eq("id", id).single();
    if (e) return onToast(errText(e), "danger");
    setOpen({ row: data });
  }
  async function remove(r) {
    if (!window.confirm(t("Padam \"{name}\" dan gambarnya?", "Delete \"{name}\" and its pictures?", { name: r.name }))) return;
    const { data, error: e } = await supabase.from(TABLES.canvas).select("preview_path,assets").eq("id", r.id).single();
    if (e) return onToast(errText(e), "danger");
    const { error: d } = await supabase.from(TABLES.canvas).delete().eq("id", r.id);
    if (d) return onToast(errText(d), "danger");
    const files = [data.preview_path, ...(data.assets || [])].filter(Boolean);
    if (files.length) await supabase.storage.from(BUCKETS.reference).remove(files);
    onToast(t("Dipadam.", "Deleted."), "info"); load();
  }

  if (open) {
    return <Editor user={user} start={open} onToast={onToast} onClose={() => { setOpen(null); load(); }} />;
  }
  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Kanvas · penyunting reka bentuk", "Kanvas · design editor")}</p>
      <h1 className="mt-2 text-4xl leading-tight">{t("Reka seperti Canva, di dalam Semasa.", "Design like Canva, inside Semasa.")}</h1>
      <p className="mt-3 max-w-2xl text-sm text-muted">
        {t("Pilih saiz, tambah teks, bentuk dan gambar, seret, ubah saiz dan warna, kemudian simpan atau muat turun PNG. Reka bentuk Wangian boleh dibuka di sini dengan setiap lapisan boleh diubah.",
          "Pick a size, add text, shapes and pictures, drag, resize and recolour, then save or download a PNG. A Wangian design opens here with every layer editable.")}
      </p>
      {error && <p className="mt-6 rounded-tile bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      <div className="mt-8 grid items-start gap-5 lg:grid-cols-[360px_1fr]">
        <Card className="min-w-0 space-y-3 p-4">
          <h2 className="text-lg">{t("Reka bentuk baharu", "New design")}</h2>
          <SizePicker value={newSize} onChange={setNewSize} />
          <Button onClick={() => setOpen({ blank: newSize })} disabled={!!error}><Plus size={14} /> {t("Buka kanvas kosong", "Open a blank canvas")}</Button>
          <p className="text-[11px] text-muted">{sizeLabel(newSize)}</p>
        </Card>
        <div className="min-w-0">
          <h2 className="mb-3 text-lg">{t("Reka bentuk saya", "My designs")}</h2>
          {!rows.length && !error && <p className="rounded-card border border-dashed border-line p-10 text-center text-sm text-muted">{t("Belum ada. Buka kanvas kosong, atau buka reka bentuk Wangian dengan \"Ubah dalam Kanvas\".", "None yet. Open a blank canvas, or open a Wangian design with \"Edit in Kanvas\".")}</p>}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((r) => (
              <Card key={r.id} className="min-w-0 overflow-hidden">
                <button type="button" onClick={() => openRow(r.id)} className="block w-full bg-surface-2" title={t("Buka", "Open")}>
                  {r.preview_url ? <img src={r.preview_url} alt="" loading="lazy" className="mx-auto h-44 w-auto object-contain" />
                    : <span className="grid h-44 place-items-center text-muted"><Layers size={24} /></span>}
                </button>
                <div className="flex items-center gap-2 p-3 text-[12px]">
                  <span className="min-w-0 flex-1">
                    <b className="block truncate">{r.name}</b>
                    <span className="block truncate text-muted">{sizeOf(r.size_id)?.name || `${r.width}×${r.height}`} · {timeAgo(r.updated_at)}</span>
                  </span>
                  {user && r.created_by === user.id && <Button size="sm" variant="danger" title={t("Padam", "Delete")} onClick={() => remove(r)}><Trash2 size={12} /></Button>}
                </div>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

function Editor({ user, start, onToast, onClose }) {
  const { t } = useLang();
  const wrapRef = useRef(null);
  const elRef = useRef(null);
  const fcRef = useRef(null);
  const zoomRef = useRef(1);
  const hist = useRef({ stack: [], at: -1, quiet: false });
  const pending = useRef([]);                                // uploads not yet saved into a design
  const guides = useRef([]);
  const [dims, setDims] = useState(() => {
    if (start.row) return { w: start.row.width, h: start.row.height, sizeId: start.row.size_id };
    if (start.seed) return { w: start.seed.width, h: start.seed.height, sizeId: start.seed.sizeId || null };
    const s = sizeOf(start.blank) || sizeOf("ig_post_45");
    return { w: s.w, h: s.h, sizeId: s.id };
  });
  const [name, setName] = useState(start.row?.name || start.seed?.name || t("Reka bentuk baharu", "New design"));
  const [rowId, setRowId] = useState(start.row?.id || null);
  const [assets, setAssets] = useState(start.row?.assets || []);
  const [previewPath, setPreviewPath] = useState(start.row?.preview_path || null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState("");
  const [sel, setSel] = useState(null);                      // a snapshot of the selected object's editable values
  const [layers, setLayers] = useState([]);
  const [panel, setPanel] = useState("text");
  const [bg, setBg] = useState("#ffffff");
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [resizeTo, setResizeTo] = useState(dims.sizeId || "ig_post_45");

  // --- history ------------------------------------------------------------------------------------------------------
  const refreshLayers = useCallback(() => {
    const fc = fcRef.current;
    if (!fc) return;
    setLayers(fc.getObjects().filter((o) => !o.excludeFromExport).map((o, i) => ({ i, o, name: o.name || typeLabel(o), visible: o.visible !== false,
      locked: !!o.lockMovementX })).reverse());
  }, []);
  const snapshot = useCallback(() => {
    const fc = fcRef.current;
    const h = hist.current;
    if (!fc || h.quiet) return;
    const json = JSON.stringify(fc.toObject(PROPS));
    if (h.stack[h.at] === json) return;
    h.stack = h.stack.slice(0, h.at + 1).concat(json).slice(-HISTORY_MAX);
    h.at = h.stack.length - 1;
    setCanUndo(h.at > 0); setCanRedo(false);
    refreshLayers();
  }, [refreshLayers]);
  async function restore(to) {
    const fc = fcRef.current;
    const h = hist.current;
    if (!fc || to < 0 || to >= h.stack.length) return;
    h.quiet = true;
    await fc.loadFromJSON(JSON.parse(h.stack[to]));
    fc.requestRenderAll();
    h.quiet = false;
    h.at = to;
    setCanUndo(to > 0); setCanRedo(to < h.stack.length - 1);
    setBg(typeof fc.backgroundColor === "string" ? fc.backgroundColor : "#ffffff");
    setSel(null); refreshLayers();
  }

  // --- the canvas ---------------------------------------------------------------------------------------------------
  const fit = useCallback(() => {
    const fc = fcRef.current;
    const wrap = wrapRef.current;
    if (!fc || !wrap) return;
    const maxW = Math.max(200, wrap.clientWidth - 16);
    const maxH = Math.max(260, window.innerHeight * 0.68);
    const z = Math.min(maxW / dims.w, maxH / dims.h, 1);
    zoomRef.current = z;
    fc.setDimensions({ width: Math.round(dims.w * z), height: Math.round(dims.h * z) });
    fc.setZoom(z);
    fc.requestRenderAll();
  }, [dims.w, dims.h]);
  const fitRef = useRef(fit);
  fitRef.current = fit;                    // the window's resize listener is added once: it must reach today's size

  useEffect(() => {
    let alive = true;
    const fc = new Canvas(elRef.current, { preserveObjectStacking: true, backgroundColor: "#ffffff", width: 10, height: 10 });
    fcRef.current = fc;
    const onSel = () => setSel(readSel(fc.getActiveObject()));
    fc.on("selection:created", onSel);
    fc.on("selection:updated", onSel);
    fc.on("selection:cleared", () => setSel(null));
    fc.on("object:modified", () => { clearGuides(fc); onSel(); snapshot(); });
    fc.on("text:changed", () => { onSel(); });
    fc.on("text:editing:exited", () => snapshot());
    fc.on("object:moving", (e) => snapToCentre(fc, e.target));
    fc.on("mouse:up", () => clearGuides(fc));
    (async () => {
      await loadFonts();
      if (!alive) return;
      hist.current.quiet = true;
      try {
        if (start.row?.doc && Object.keys(start.row.doc).length) {
          await fc.loadFromJSON(start.row.doc);
          setBg(typeof fc.backgroundColor === "string" ? fc.backgroundColor : "#ffffff");
        } else if (start.seed) {
          await buildSeed(fc, start.seed, user, (p) => pending.current.push(p));
        }
      } catch (err) {
        onToast(t("Sebahagian reka bentuk tidak dapat dibuka: {e}", "Part of the design could not be opened: {e}", { e: err.message || String(err) }), "warn");
      }
      hist.current.quiet = false;
      if (!alive) return;
      fitRef.current();
      snapshot();
      setReady(true);
    })();
    const onResize = () => fitRef.current();
    window.addEventListener("resize", onResize);
    return () => {
      alive = false;
      window.removeEventListener("resize", onResize);
      fcRef.current = null;
      fc.dispose();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { fit(); }, [fit]);

  function snapToCentre(fc, o) {
    const z = zoomRef.current;
    const c = o.getCenterPoint();
    const tol = SNAP_PX / z;
    const v = Math.abs(c.x - dims.w / 2) < tol;
    const h = Math.abs(c.y - dims.h / 2) < tol;
    if (v || h) o.setPositionByOrigin(new Point(v ? dims.w / 2 : c.x, h ? dims.h / 2 : c.y), "center", "center");
    clearGuides(fc, true);
    const style = { stroke: "#ec4899", strokeWidth: 1.5 / z, selectable: false, evented: false, excludeFromExport: true };
    if (v) guides.current.push(new Line([dims.w / 2, 0, dims.w / 2, dims.h], style));
    if (h) guides.current.push(new Line([0, dims.h / 2, dims.w, dims.h / 2], style));
    guides.current.forEach((g) => fc.add(g));
  }
  function clearGuides(fc, silent) {
    guides.current.forEach((g) => fc.remove(g));
    guides.current = [];
    if (!silent) fc.requestRenderAll();
  }

  // --- adding things ------------------------------------------------------------------------------------------------
  function add(obj, nameOf) {
    const fc = fcRef.current;
    obj.name = nameOf;
    fc.add(obj);
    fc.setActiveObject(obj);
    fc.requestRenderAll();
    snapshot();
  }
  const u = Math.min(dims.w, dims.h);
  function addText(kind) {
    const spec = { heading: [t("Tajuk anda", "Your headline"), "Playfair Display", 800, 0.11],
      sub: [t("Subtajuk", "Subheading"), "Poppins", 700, 0.055], body: [t("Tulis teks anda di sini", "Write your text here"), "Instrument Sans", 400, 0.035] }[kind];
    add(new Textbox(spec[0], { left: dims.w / 2, top: dims.h / 2, width: dims.w * 0.7, fontFamily: spec[1], fontWeight: spec[2],
      fontSize: u * spec[3], fill: "#111111", textAlign: "center", lineHeight: 1.1 }), spec[0]);
  }
  function addShape(kind) {
    const s = u * 0.3;
    const base = { left: dims.w / 2, top: dims.h / 2, fill: "#d4a853" };
    if (kind === "rect") add(new Rect({ ...base, width: s, height: s, rx: s * 0.06, ry: s * 0.06 }), t("Segi empat", "Rectangle"));
    if (kind === "circle") add(new Circle({ ...base, radius: s / 2 }), t("Bulatan", "Circle"));
    if (kind === "triangle") add(new Triangle({ ...base, width: s, height: s }), t("Segi tiga", "Triangle"));
    if (kind === "line") add(new Line([dims.w / 2 - s, dims.h / 2, dims.w / 2 + s, dims.h / 2], { stroke: "#111111", strokeWidth: u * 0.006 }), t("Garisan", "Line"));
    if (kind === "badge") add(makeBadge(t("Lencana", "Badge"), dims.w / 2, dims.h / 2, u * 0.15), t("Lencana", "Badge"));
  }
  async function addPicture(file, asBackground) {
    const why = refusal(file);
    if (why) return onToast(why, "warn");
    setBusy("upload");
    try {
      const up = await uploadReference(user, file);
      pending.current.push(up.path);
      setAssets((a) => [...a, up.path]);
      const img = await FabricImage.fromURL(up.url, { crossOrigin: "anonymous" });
      if (asBackground) coverImage(img, dims.w, dims.h);
      else { const k = Math.min((dims.w * 0.6) / img.width, (dims.h * 0.6) / img.height, 1); img.set({ left: dims.w / 2, top: dims.h / 2, scaleX: k, scaleY: k }); }
      img.name = asBackground ? t("Latar", "Background") : (file.name || t("Gambar", "Picture"));
      img.role = asBackground ? "bg" : undefined;
      const fc = fcRef.current;
      fc.add(img);
      if (asBackground) fc.sendObjectToBack(img);
      fc.setActiveObject(img);
      fc.requestRenderAll();
      snapshot();
    } catch (err) {
      onToast(err.message || String(err), "danger");
    } finally { setBusy(""); }
  }

  // --- the selection ------------------------------------------------------------------------------------------------
  function active() { return fcRef.current?.getActiveObject(); }
  function change(patch) {
    const fc = fcRef.current;
    const o = active();
    if (!o) return;
    const targets = o.type === "activeselection" ? o.getObjects() : [o];
    for (const x of targets) {
      const p = { ...patch };
      if ("fontSize" in p && x.scaleY) p.fontSize = p.fontSize / x.scaleY;       // the size shown is the size drawn
      if ("fontFamily" in p && x.fontWeight) p.fontWeight = nearestWeight(p.fontFamily, Number(x.fontWeight) || 400);
      if ("fontWeight" in p) p.fontWeight = nearestWeight(x.fontFamily, p.fontWeight);
      x.set(p);
      if (x.initDimensions) x.initDimensions();
      x.setCoords();
    }
    fc.requestRenderAll();
    setSel(readSel(o));
    snapshot();
  }
  function order(dir) {
    const fc = fcRef.current;
    const o = active();
    if (!o) return;
    if (dir === "up") fc.bringObjectForward(o); else if (dir === "down") fc.sendObjectBackwards(o);
    else if (dir === "top") fc.bringObjectToFront(o); else fc.sendObjectToBack(o);
    fc.requestRenderAll(); snapshot();
  }
  async function duplicate() {
    const fc = fcRef.current;
    const o = active();
    if (!o) return;
    const copy = await o.clone(PROPS);
    copy.set({ left: o.left + u * 0.03, top: o.top + u * 0.03 });
    copy.name = `${o.name || typeLabel(o)} (2)`;
    fc.add(copy); fc.setActiveObject(copy); fc.requestRenderAll(); snapshot();
  }
  function removeSel() {
    const fc = fcRef.current;
    const o = active();
    if (!o) return;
    (o.type === "activeselection" ? o.getObjects() : [o]).forEach((x) => fc.remove(x));
    fc.discardActiveObject(); fc.requestRenderAll(); setSel(null); snapshot();
  }
  function centre(axis) {
    const o = active();
    if (!o) return;
    const c = o.getCenterPoint();
    o.setPositionByOrigin(new Point(axis === "h" ? dims.w / 2 : c.x, axis === "v" ? dims.h / 2 : c.y), "center", "center");
    o.setCoords(); fcRef.current.requestRenderAll(); snapshot();
  }
  function toggleLock(o) {
    const on = !o.lockMovementX;
    o.set({ lockMovementX: on, lockMovementY: on, lockScalingX: on, lockScalingY: on, lockRotation: on, hasControls: !on });
    fcRef.current.requestRenderAll(); snapshot();
  }
  function toggleVisible(o) {
    o.set({ visible: o.visible === false });
    if (o.visible === false) fcRef.current.discardActiveObject();
    fcRef.current.requestRenderAll(); snapshot();
  }

  // Canva's Resize: every object keeps its place relative to the card and keeps its proportions; a background is
  // cover-fitted to the new shape
  function resize(id) {
    const s = sizeOf(id);
    const fc = fcRef.current;
    if (!s || !fc) return;
    const sx = s.w / dims.w;
    const sy = s.h / dims.h;
    const k = Math.min(sx, sy);
    fc.getObjects().filter((o) => !o.excludeFromExport).forEach((o) => {
      if (o.role === "bg" && o.type === "image") { coverImage(o, s.w, s.h); return; }
      const c = o.getCenterPoint();
      o.set({ scaleX: o.scaleX * k, scaleY: o.scaleY * k });
      o.setPositionByOrigin(new Point(c.x * sx, c.y * sy), "center", "center");
      o.setCoords();
    });
    setDims({ w: s.w, h: s.h, sizeId: id });
    setTimeout(snapshot, 0);
  }
  function setBackground(color) {
    setBg(color);
    const fc = fcRef.current;
    fc.backgroundColor = color;
    fc.requestRenderAll();
    snapshot();
  }

  // --- keyboard -----------------------------------------------------------------------------------------------------
  useEffect(() => {
    const onKey = (e) => {
      const tag = (e.target?.tagName || "").toLowerCase();
      const o = active();
      if (tag === "input" || tag === "textarea" || tag === "select" || o?.isEditing) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); restore(hist.current.at + (e.shiftKey ? 1 : -1)); return; }
      if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); restore(hist.current.at + 1); return; }
      if (mod && e.key.toLowerCase() === "d") { e.preventDefault(); duplicate(); return; }
      if (!o) return;
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); removeSel(); return; }
      const step = e.shiftKey ? 10 : 1;
      const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
      if (d) { e.preventDefault(); o.set({ left: o.left + d[0], top: o.top + d[1] }); o.setCoords(); fcRef.current.requestRenderAll(); snapshot(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // --- save / download ----------------------------------------------------------------------------------------------
  function picture(format = "png") {
    const fc = fcRef.current;
    fc.discardActiveObject();
    clearGuides(fc, true);
    fc.renderAll();
    return fc.toDataURL({ format, quality: 0.92, multiplier: 1 / zoomRef.current });
  }
  function download(format) {
    try {
      const url = picture(format);
      const a = document.createElement("a");
      a.href = url; a.download = `${(name || "kanvas").replace(/[^\w-]+/g, "-").slice(0, 60)}.${format === "jpeg" ? "jpg" : "png"}`;
      a.click();
    } catch (err) { onToast(tainted(err, t), "danger"); }
  }
  async function save() {
    const fc = fcRef.current;
    setBusy("save");
    try {
      const doc = fc.toObject(PROPS);
      const json = JSON.stringify(doc);
      if (json.includes('"src":"data:')) throw new Error(t("Ada gambar yang tidak dimuat naik; buang dan tambah semula.", "A picture was not uploaded; remove it and add it again."));
      if (json.length > 1_200_000) throw new Error(t("Reka bentuk terlalu besar untuk disimpan.", "The design is too large to save."));
      let png;
      try { png = picture("png"); } catch (err) { throw new Error(tainted(err, t)); }
      const blob = await (await fetch(png)).blob();
      const up = await uploadReference(user, new File([blob], `kanvas-${Date.now()}.png`, { type: "image/png" }));
      const fields = { name: name.trim() || t("Reka bentuk", "Design"), width: dims.w, height: dims.h, size_id: dims.sizeId || null,
        doc, preview_url: up.url, preview_path: up.path, assets,
        ...(start.seed?.source ? { source: start.seed.source, source_id: start.seed.sourceId || null } : {}) };
      const q = rowId ? supabase.from(TABLES.canvas).update(fields).eq("id", rowId)
        : supabase.from(TABLES.canvas).insert({ ...fields, created_by: user.id });
      const { data, error } = await q.select("id").single();
      if (error) { await supabase.storage.from(BUCKETS.reference).remove([up.path]); throw new Error(errText(error)); }
      if (previewPath && previewPath !== up.path) await supabase.storage.from(BUCKETS.reference).remove([previewPath]);
      setPreviewPath(up.path); setRowId(data.id);
      pending.current = [];
      onToast(t("Disimpan.", "Saved."), "ok");
    } catch (err) {
      onToast(err.message || String(err), "danger");
    } finally { setBusy(""); }
  }
  async function close() {
    // pictures uploaded into a design that was never saved belong to nothing: they go with it
    if (pending.current.length) {
      if (!window.confirm(t("Tutup tanpa simpan? Perubahan terakhir hilang.", "Close without saving? The last changes are lost."))) return;
      await supabase.storage.from(BUCKETS.reference).remove(pending.current).catch(() => {});
    }
    onClose();
  }

  const isText = sel && ["textbox", "i-text", "text"].includes(sel.type);
  return (
    <main className="mx-auto max-w-page px-2 pb-16 pt-4 sm:px-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" onClick={close}><ArrowLeft size={13} /> {t("Kembali", "Back")}</Button>
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} aria-label={t("Nama reka bentuk", "Design name")} className="!w-56 !py-1.5 text-xs" />
        <span className="text-[11px] text-muted">{sizeOf(dims.sizeId)?.name || t("Saiz sendiri", "Custom size")} · {dims.w}×{dims.h}</span>
        <span className="ml-auto flex flex-wrap gap-1">
          <Button size="sm" variant="soft" disabled={!canUndo} onClick={() => restore(hist.current.at - 1)} title={t("Buat asal (Ctrl+Z)", "Undo (Ctrl+Z)")} aria-label={t("Buat asal", "Undo")}><Undo2 size={13} /></Button>
          <Button size="sm" variant="soft" disabled={!canRedo} onClick={() => restore(hist.current.at + 1)} title={t("Buat semula (Ctrl+Y)", "Redo (Ctrl+Y)")} aria-label={t("Buat semula", "Redo")}><Redo2 size={13} /></Button>
          <Button size="sm" variant="soft" disabled={!ready} onClick={() => download("png")}><Download size={13} /> PNG</Button>
          <Button size="sm" variant="soft" disabled={!ready} onClick={() => download("jpeg")}><Download size={13} /> JPG</Button>
          <Button size="sm" disabled={!ready || !!busy} onClick={save}>{busy === "save" ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} {t("Simpan", "Save")}</Button>
        </span>
      </div>

      <div className="mt-3 grid items-start gap-3 lg:grid-cols-[250px_1fr_230px]">
        {/* tools */}
        <Card className="min-w-0 p-3 text-[12px]">
          <div className="flex flex-wrap gap-1" role="tablist">
            {[["text", t("Teks", "Text")], ["shapes", t("Elemen", "Elements")], ["pictures", t("Gambar", "Pictures")], ["bg", t("Latar", "Background")], ["size", t("Saiz", "Resize")]].map(([k, l]) => (
              <button type="button" key={k} role="tab" aria-selected={panel === k} onClick={() => setPanel(k)}
                className={`rounded-pill border px-2.5 py-1 ${panel === k ? "border-accent bg-surface-2" : "border-line text-muted"}`}>{l}</button>
            ))}
          </div>
          <div className="mt-3 space-y-2">
            {panel === "text" && <>
              <button type="button" onClick={() => addText("heading")} className="block w-full rounded-tile border border-line p-2 text-left hover:bg-surface-2" style={{ fontFamily: "Playfair Display", fontWeight: 800, fontSize: 20 }}>{t("Tambah tajuk", "Add a heading")}</button>
              <button type="button" onClick={() => addText("sub")} className="block w-full rounded-tile border border-line p-2 text-left hover:bg-surface-2" style={{ fontFamily: "Poppins", fontWeight: 700, fontSize: 15 }}>{t("Tambah subtajuk", "Add a subheading")}</button>
              <button type="button" onClick={() => addText("body")} className="block w-full rounded-tile border border-line p-2 text-left hover:bg-surface-2">{t("Tambah teks", "Add body text")}</button>
            </>}
            {panel === "shapes" && <div className="grid grid-cols-3 gap-1.5">
              {[["rect", Square, t("Segi empat", "Rectangle")], ["circle", CircleIcon, t("Bulatan", "Circle")], ["triangle", TriangleIcon, t("Segi tiga", "Triangle")], ["line", Minus, t("Garisan", "Line")], ["badge", CircleIcon, t("Lencana", "Badge")]].map(([k, Icon, l]) => (
                <button type="button" key={k} onClick={() => addShape(k)} className="flex flex-col items-center gap-1 rounded-tile border border-line p-2 hover:bg-surface-2"><Icon size={18} /><span className="text-[10px]">{l}</span></button>
              ))}
            </div>}
            {panel === "pictures" && <>
              <label className="flex cursor-pointer items-center gap-2 rounded-tile border border-dashed border-line p-3 hover:bg-surface-2">
                {busy === "upload" ? <Loader2 size={15} className="animate-spin" /> : <ImagePlus size={15} />} {t("Muat naik gambar", "Upload a picture")}
                <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) addPicture(f, false); }} />
              </label>
              <p className="text-muted">{t("PNG lutsinar (botol, logo) kekal lutsinar.", "A transparent PNG (bottle, logo) stays transparent.")}</p>
            </>}
            {panel === "bg" && <>
              <label className="flex items-center gap-2"><input type="color" value={bg} onChange={(e) => setBackground(e.target.value)} aria-label={t("Warna latar", "Background colour")} /> {t("Warna latar", "Background colour")}</label>
              <div className="flex flex-wrap gap-1">{["#ffffff", "#111111", "#2b2113", "#f5efe6", "#e8c98a", "#7a1f2b", "#1f3a5f", "#e9f0ea"].map((c) => (
                <button type="button" key={c} onClick={() => setBackground(c)} className="h-6 w-6 rounded border border-line" style={{ background: c }} aria-label={c} />))}</div>
              <label className="flex cursor-pointer items-center gap-2 rounded-tile border border-dashed border-line p-3 hover:bg-surface-2">
                <ImagePlus size={15} /> {t("Gambar sebagai latar", "Picture as background")}
                <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) addPicture(f, true); }} />
              </label>
            </>}
            {panel === "size" && <>
              <SizePicker value={resizeTo} onChange={setResizeTo} />
              <Button size="sm" onClick={() => resize(resizeTo)} disabled={resizeTo === dims.sizeId}><Maximize2 size={12} /> {t("Ubah saiz ke {size}", "Resize to {size}", { size: sizeOf(resizeTo)?.name || "" })}</Button>
              <p className="text-muted">{t("Semua elemen kekal di tempat yang sama pada kad; latar diisi semula.", "Everything keeps its place on the card; the background is refilled.")}</p>
            </>}
          </div>
        </Card>

        {/* the card */}
        <div ref={wrapRef} className="min-w-0">
          <div className="flex min-h-[260px] items-start justify-center rounded-card bg-surface-2 p-2">
            <div className="relative shadow-lift" style={{ lineHeight: 0 }}>
              <canvas ref={elRef} aria-label={t("Kanvas reka bentuk", "Design canvas")} />
              {!ready && <span className="absolute inset-0 grid place-items-center bg-surface/70 text-muted"><Loader2 className="animate-spin" /></span>}
            </div>
          </div>
          {sel && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 rounded-tile border border-line bg-surface p-2 text-[12px]">
              {isText && <>
                <select value={sel.fontFamily} onChange={(e) => change({ fontFamily: e.target.value })} className="rounded-pill border border-line bg-bg px-2 py-1" aria-label={t("Fon", "Font")}>
                  {Object.keys(FONTS).map((f) => <option key={f} value={f} style={{ fontFamily: f }}>{f}</option>)}
                </select>
                <input type="number" min={6} max={800} value={Math.round(sel.fontSize)} onChange={(e) => change({ fontSize: Math.max(6, Number(e.target.value) || 6) })} className="w-16 rounded-pill border border-line bg-bg px-2 py-1" aria-label={t("Saiz fon", "Font size")} />
                <Button size="sm" variant={sel.bold ? "primary" : "soft"} onClick={() => change({ fontWeight: sel.bold ? 400 : 800 })} aria-label={t("Tebal", "Bold")}><Bold size={12} /></Button>
                <Button size="sm" variant={sel.italic ? "primary" : "soft"} onClick={() => change({ fontStyle: sel.italic ? "normal" : "italic" })} aria-label={t("Condong", "Italic")}><Italic size={12} /></Button>
                <select value={sel.textAlign} onChange={(e) => change({ textAlign: e.target.value })} className="rounded-pill border border-line bg-bg px-2 py-1" aria-label={t("Jajaran", "Alignment")}>
                  <option value="left">{t("Kiri", "Left")}</option><option value="center">{t("Tengah", "Centre")}</option><option value="right">{t("Kanan", "Right")}</option>
                </select>
                <label className="flex items-center gap-1">{t("Jarak", "Spacing")}<input type="range" min={-50} max={600} value={sel.charSpacing} onChange={(e) => change({ charSpacing: Number(e.target.value) })} aria-label={t("Jarak huruf", "Letter spacing")} /></label>
              </>}
              {sel.hasFill && <label className="flex items-center gap-1">{t("Warna", "Colour")}<input type="color" value={sel.fill} onChange={(e) => change({ fill: e.target.value })} aria-label={t("Warna", "Colour")} /></label>}
              {sel.type === "line" && <label className="flex items-center gap-1">{t("Warna", "Colour")}<input type="color" value={sel.stroke} onChange={(e) => change({ stroke: e.target.value })} aria-label={t("Warna garisan", "Line colour")} /></label>}
              <label className="flex items-center gap-1">{t("Legap", "Opacity")}<input type="range" min={5} max={100} value={Math.round(sel.opacity * 100)} onChange={(e) => change({ opacity: Number(e.target.value) / 100 })} aria-label={t("Kelegapan", "Opacity")} /></label>
              <span className="ml-auto flex flex-wrap gap-1">
                <Button size="sm" variant="soft" onClick={() => centre("h")} title={t("Tengah mendatar", "Centre horizontally")} aria-label={t("Tengah mendatar", "Centre horizontally")}><AlignCenterVertical size={12} /></Button>
                <Button size="sm" variant="soft" onClick={() => centre("v")} title={t("Tengah menegak", "Centre vertically")} aria-label={t("Tengah menegak", "Centre vertically")}><AlignCenterHorizontal size={12} /></Button>
                <Button size="sm" variant="soft" onClick={() => order("up")} title={t("Ke depan", "Forward")} aria-label={t("Ke depan", "Forward")}><ArrowUp size={12} /></Button>
                <Button size="sm" variant="soft" onClick={() => order("down")} title={t("Ke belakang", "Backward")} aria-label={t("Ke belakang", "Backward")}><ArrowDown size={12} /></Button>
                <Button size="sm" variant="soft" onClick={duplicate} title={t("Salin (Ctrl+D)", "Duplicate (Ctrl+D)")} aria-label={t("Salin", "Duplicate")}><Copy size={12} /></Button>
                <Button size="sm" variant="danger" onClick={removeSel} title={t("Padam (Delete)", "Delete (Delete)")} aria-label={t("Padam elemen", "Delete element")}><Trash2 size={12} /></Button>
              </span>
            </div>
          )}
        </div>

        {/* layers */}
        <Card className="min-w-0 p-3 text-[12px]">
          <h3 className="mb-2 flex items-center gap-1.5 font-semibold"><Layers size={13} /> {t("Lapisan", "Layers")}</h3>
          {!layers.length && <p className="text-muted">{t("Kosong.", "Empty.")}</p>}
          <ul className="space-y-1">
            {layers.map((l) => (
              <li key={`${l.i}-${l.name}`} className={`flex items-center gap-1 rounded-tile border px-2 py-1 ${active() === l.o ? "border-accent bg-surface-2" : "border-line"}`}>
                <button type="button" className="min-w-0 flex-1 truncate text-left" onClick={() => { const fc = fcRef.current; if (l.visible) { fc.setActiveObject(l.o); fc.requestRenderAll(); setSel(readSel(l.o)); } }}>{l.name}</button>
                <button type="button" onClick={() => toggleVisible(l.o)} aria-label={l.visible ? t("Sembunyi", "Hide") : t("Tunjuk", "Show")} className="text-muted hover:text-ink">{l.visible ? <Eye size={12} /> : <EyeOff size={12} />}</button>
                <button type="button" onClick={() => toggleLock(l.o)} aria-label={l.locked ? t("Buka kunci", "Unlock") : t("Kunci", "Lock")} className="text-muted hover:text-ink">{l.locked ? <Lock size={12} /> : <Unlock size={12} />}</button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] text-muted">{t("Seret untuk alih; sudut untuk ubah saiz. Garis merah jambu = tepat di tengah. Anak panah: alih 1px (Shift: 10px).", "Drag to move; corners to resize. A pink line means dead centre. Arrow keys nudge 1px (Shift: 10px).")}</p>
          {start.seed?.source === "fragrance" && <p className="mt-2 text-[11px] text-warn">{t("Lencana hanya dakwaan yang anda luluskan: jangan tambah dakwaan baharu di sini tanpa bukti dalam PIF.", "Badges carry only the claims you approved: do not add a new claim here without evidence in the PIF.")}</p>}
        </Card>
      </div>
    </main>
  );
}

// --- helpers --------------------------------------------------------------------------------------------------------

function typeLabel(o) {
  return { textbox: "Teks", image: "Gambar", rect: "Segi empat", circle: "Bulatan", triangle: "Segi tiga", line: "Garisan", group: "Kumpulan" }[o.type] || o.type;
}

function readSel(o) {
  if (!o) return null;
  const fill = typeof o.fill === "string" && /^#[0-9a-f]{6}$/i.test(o.fill) ? o.fill : null;
  return {
    type: o.type, fontFamily: o.fontFamily, fontSize: (o.fontSize || 0) * (o.scaleY || 1), bold: Number(o.fontWeight) >= 600,
    italic: o.fontStyle === "italic", textAlign: o.textAlign || "left", charSpacing: o.charSpacing || 0,
    opacity: o.opacity ?? 1, hasFill: !!fill && o.type !== "image" && o.type !== "line", fill: fill || "#000000",
    stroke: typeof o.stroke === "string" ? o.stroke : "#000000",
  };
}

function coverImage(img, w, h) {
  const k = Math.max(w / img.width, h / img.height);
  img.set({ left: w / 2, top: h / 2, scaleX: k, scaleY: k, angle: 0 });
  img.setCoords();
}

function makeBadge(text, x, y, d) {
  const disc = new Circle({ left: x, top: y, radius: d / 2,
    fill: new Gradient({ type: "radial", gradientUnits: "percentage",
      coords: { x1: 0.35, y1: 0.3, r1: 0, x2: 0.35, y2: 0.3, r2: 0.8 },
      colorStops: [{ offset: 0, color: "#fbf1d0" }, { offset: 0.45, color: "#e3c888" }, { offset: 1, color: "#b8914a" }] }),
    shadow: new Shadow({ color: "rgba(0,0,0,0.28)", blur: d * 0.12, offsetY: d * 0.04 }) });
  const words = new Textbox(text, { left: x, top: y, width: d * 0.76, fontFamily: "Poppins", fontWeight: 800, fontSize: d * 0.14,
    lineHeight: 1.1, fill: "#2b2113", textAlign: "center" });
  return new Group([disc, words], { left: x, top: y });
}

function tainted(err, t) {
  return /taint|SecurityError|insecure/i.test(String(err?.name || err?.message || err))
    ? t("Satu gambar datang dari laman lain yang tidak membenarkan eksport; buang gambar itu dan muat naik salinannya sendiri.",
      "A picture comes from a site that does not allow export; remove it and upload your own copy.")
    : (err?.message || String(err));
}

// A Wangian design (lib/canvasSeed.js) as Fabric objects. Its pictures are copied into the uploads bucket first:
// the worker's own files are deleted with the design job (7 days unsaved, or the version not kept), and a Kanvas
// design must not lose its background the week after.
async function buildSeed(fc, seed, user, own) {
  fc.backgroundColor = "#111111";
  const byName = {};
  for (const L of seed.layers) {
    let obj = null;
    if (L.kind === "image") {
      let url = L.url;
      try {
        const blob = await (await fetch(url, { mode: "cors" })).blob();
        const ext = blob.type === "image/png" ? "png" : "jpg";
        const up = await uploadReference(user, new File([blob], `kanvas-${L.role || "gambar"}.${ext}`, { type: blob.type || "image/jpeg" }));
        own(up.path);
        url = up.url;
      } catch { /* keep the worker's address: it still opens, and saving warns nothing extra */ }
      obj = await FabricImage.fromURL(url, { crossOrigin: "anonymous" });
      if (L.cover) coverImage(obj, seed.width, seed.height);
      else {
        const k = L.height / obj.height;
        const wd = obj.width * k;
        const x = L.side === "left" ? L.xLeft + wd / 2 : L.side === "right" ? L.xRight - wd / 2 : L.x;
        const y = L.bottomY != null ? L.bottomY - L.height / 2 : L.top + L.height / 2;
        obj.set({ left: x, top: y, scaleX: k, scaleY: k });
        if (L.shadow) obj.shadow = new Shadow({ color: "rgba(0,0,0,0.3)", blur: 24, offsetY: 18 });
      }
      obj.role = L.role;
    } else if (L.kind === "text") {
      obj = new Textbox(L.text, { left: L.x, top: 0, width: L.width, fontFamily: L.font, fontWeight: L.weight,
        fontStyle: L.italic ? "italic" : "normal", fontSize: L.size, lineHeight: L.lineHeight || 1.16, charSpacing: L.spacing || 0,
        fill: L.fill, textAlign: L.align || "center" });
      if (L.shadow) obj.shadow = TEXT_SHADOW();
      if (L.fit) {                       // like the CSS: the big line shrinks until it fits its box, never cut
        // a Textbox widens itself to its longest word (dynamicMinWidth): shrink until that word fits the box
        while (obj.width > L.width + 1 && obj.fontSize > 12) { obj.set({ fontSize: obj.fontSize * 0.94, width: L.width }); obj.initDimensions(); }
      }
      const prev = L.below ? byName[L.below] : null;
      const topEdge = prev ? prev.top + prev.height / 2 + (L.gap || 0) : L.top;
      obj.set({ top: topEdge + obj.height / 2 });
    } else if (L.kind === "badge") {
      obj = makeBadge(L.text, L.x, L.y, L.d);
    }
    if (!obj) continue;
    obj.name = L.name;
    byName[L.name] = obj;
    fc.add(obj);
    if (L.under && byName[L.under]) fc.moveObjectTo(obj, fc.getObjects().indexOf(byName[L.under]));
  }
  fc.requestRenderAll();
}

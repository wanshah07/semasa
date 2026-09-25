import { useEffect, useState } from "react";
import { Lock, Save } from "lucide-react";
import { DAY_NAMES } from "../lib/brand";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import { Input, Label } from "../components/ui/Field";

const SLOT = /^([01]\d|2[0-3]):[0-5]\d$/;
const parseSlots = (s) => [...new Set(s.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean))].sort();

/* Studio's Settings, the parts Semasa uses now: posting positions and the weekly rota.
   The publishing switch is shown, never editable: the database refuses it from the browser. */
export default function SettingsTab({ settings, brand, save, onToast }) {
  const [regSlots, setRegSlots] = useState("");
  const [liSlots, setLiSlots] = useState("");
  const [liDays, setLiDays] = useState([]);
  const [rota, setRota] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRegSlots((brand.regulab.slots || []).join(", "));
    setLiSlots((brand.linkedin.slots || []).join(", "));
    setLiDays(brand.linkedin.days || []);
    setRota(Object.fromEntries([0, 1, 2, 3, 4, 5, 6].map((d) => [d, [...((brand.regulab.schedule || {})[d] || [])]])));
  }, [brand]);

  const domains = Object.entries(brand.regulab.domains || {});
  const publishing = settings.publishing || {};

  function toggle(day, dom) {
    setRota((r) => ({ ...r, [day]: r[day].includes(dom) ? r[day].filter((x) => x !== dom) : [...r[day], dom] }));
  }

  async function submit() {
    const rs = parseSlots(regSlots), ls = parseSlots(liSlots);
    const bad = [...rs, ...ls].filter((x) => !SLOT.test(x));
    if (bad.length) return onToast(`Masa tidak sah: ${bad.join(", ")} (guna HH:MM)`, "warn");
    if (!rs.length || !ls.length) return onToast("Setiap aliran perlukan sekurang-kurangnya satu slot.", "warn");
    const current = settings.brand || {};
    const next = {
      ...current,
      regulab: { ...(current.regulab || {}), slots: rs,
        schedule: Object.fromEntries(Object.entries(rota).map(([d, list]) => [String(d), list])) },
      linkedin: { ...(current.linkedin || {}), slots: ls, days: [...liDays].sort() },
    };
    setBusy(true);
    try { await save("brand", next); onToast("Tetapan disimpan.", "ok"); } catch (e) { onToast(e.message, "danger"); }
    setBusy(false);
  }

  return (
    <main className="mx-auto max-w-page space-y-5 px-4 pb-20 pt-10 sm:px-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Tetapan</p>
        <h1 className="mt-2 text-4xl leading-tight">Slot dan giliran mingguan.</h1>
      </div>

      <Card className="flex items-start gap-3 p-5">
        <Lock size={18} className={publishing.enabled ? "text-ok" : "text-warn"} />
        <div>
          <h3 className="text-lg">Penerbitan: {publishing.enabled ? "HIDUP" : "MATI"}</h3>
          <p className="mt-1 text-sm text-muted">{publishing.why || ""}</p>
          <p className="mt-1 text-[12px] text-muted">Suis ini tidak boleh diubah dari laman ini. Ia diubah di Supabase SQL editor sahaja.</p>
        </div>
      </Card>

      <Card className="grid gap-4 p-5 sm:grid-cols-2">
        <label className="block"><Label hint="HH:MM, dipisah koma">Slot ws.regulab (MYT)</Label>
          <Input value={regSlots} onChange={(e) => setRegSlots(e.target.value)} /></label>
        <label className="block"><Label hint="HH:MM, dipisah koma">Slot LinkedIn (MYT)</Label>
          <Input value={liSlots} onChange={(e) => setLiSlots(e.target.value)} /></label>
        <div className="sm:col-span-2">
          <Label>Hari LinkedIn</Label>
          <div className="flex flex-wrap gap-3 text-sm">
            {DAY_NAMES.map((n, d) => (
              <label key={d} className="flex items-center gap-1.5">
                <input type="checkbox" checked={liDays.includes(d)}
                  onChange={() => setLiDays((x) => (x.includes(d) ? x.filter((y) => y !== d) : [...x, d]))} /> {n}
              </label>
            ))}
          </div>
        </div>
      </Card>

      <Card className="overflow-x-auto p-5">
        <Label hint="hari tanpa domain = tiada post ws.regulab">Giliran ws.regulab</Label>
        <table className="mt-2 w-full min-w-[640px] text-left text-xs">
          <thead>
            <tr><th className="py-1 pr-2 font-medium text-muted">Hari</th>
              {domains.map(([k, l]) => <th key={k} className="px-1 py-1 font-medium text-muted" title={l}>{k}</th>)}</tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4, 5, 6, 0].map((d) => (
              <tr key={d} className="border-t border-line/70">
                <td className="py-1.5 pr-2">{DAY_NAMES[d]}</td>
                {domains.map(([k]) => (
                  <td key={k} className="px-1 py-1.5">
                    <input type="checkbox" aria-label={`${DAY_NAMES[d]} ${k}`} checked={(rota[d] || []).includes(k)} onChange={() => toggle(d, k)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Button onClick={submit} disabled={busy}><Save size={14} /> Simpan tetapan</Button>
    </main>
  );
}

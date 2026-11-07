import { useMemo } from "react";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { businessList } from "../lib/businesses";
import { Label, Select } from "./ui/Field";

/* Which business a receipt or a subscription belongs to (supabase/066; empty = personal). Draws nothing before 066 is applied
   (no businesses to choose from), so the form saves exactly as it did. */
export default function BusinessSelect({ value, onChange, className = "" }) {
  const { t } = useLang();
  const bizT = useTable(TABLES.businesses, { enabled: true, order: "sort", ascending: true, limit: 50, realtime: false });
  const list = useMemo(() => businessList(bizT.rows), [bizT.rows]);
  if (bizT.error || !bizT.rows.length) return null;
  return (
    <label className={className} data-business-select><Label>{t("Syarikat (kosong = peribadi)", "Business (empty = personal)")}</Label>
      <Select className="w-full" value={value || ""} onChange={(v) => onChange(v || null)} options={[["", t("Peribadi", "Personal")], ...list.map((b) => [b.id, b.name])]} /></label>
  );
}

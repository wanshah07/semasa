import { Film, Image as ImageIcon, Trash2 } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { timeAgo } from "../lib/format";
import Button from "./ui/Button";
import Card from "./ui/Card";

/* Flow B's "keep the prompt": saved words (and their reference) to use again. */
export default function PromptLibrary({ prompts, onUse, onToast }) {
  async function remove(p) {
    const { error } = await supabase.from(TABLES.prompts).delete().eq("id", p.id);
    if (error) onToast(errText(error), "danger"); else prompts.reload();
  }
  return (
    <Card className="p-5">
      <h3 className="text-lg">Pustaka prompt</h3>
      {!prompts.rows.length && <p className="mt-2 text-sm text-muted">Belum ada. Tandakan “Simpan prompt” semasa menjana.</p>}
      <ul className="mt-3 space-y-2">
        {prompts.rows.map((p) => (
          <li key={p.id} className="flex items-start gap-3 rounded-tile border border-line p-2">
            {p.reference_url
              ? <img src={p.reference_url} alt="" className="h-12 w-12 shrink-0 rounded-tile object-cover" />
              : <span className="grid h-12 w-12 shrink-0 place-items-center rounded-tile bg-surface-2 text-muted">
                  {p.type === "video" ? <Film size={16} /> : <ImageIcon size={16} />}</span>}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{p.title || p.prompt.slice(0, 60)}</span>
              <span className="line-clamp-2 block text-[12px] text-muted">{p.prompt}</span>
              <span className="text-[11px] text-muted">{p.type} · digunakan {p.uses}× · {timeAgo(p.created_at)}</span>
            </span>
            <span className="flex shrink-0 flex-col gap-1">
              <Button size="sm" variant="soft" onClick={() => onUse(p)}>Guna</Button>
              <Button size="sm" variant="danger" onClick={() => remove(p)} title="Padam"><Trash2 size={12} /></Button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

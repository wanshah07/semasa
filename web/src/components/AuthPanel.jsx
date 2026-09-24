import { useState } from "react";
import { Mail } from "lucide-react";
import { supabase, errText } from "../lib/SupabaseClient";
import Button from "./ui/Button";
import Card from "./ui/Card";

/* Magic-link sign-in. Add your email under Authentication → Users (or allow sign-ups) in Supabase. */
export default function AuthPanel({ onToast }) {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    const { error } = await supabase.auth.signInWithOtp({
      email, options: { emailRedirectTo: window.location.href.split("#")[0] },
    });
    setBusy(false);
    if (error) onToast(errText(error), "danger"); else setSent(true);
  }

  return (
    <Card className="mx-auto max-w-md p-6">
      <h3 className="text-lg">Log masuk untuk memuat naik</h3>
      <p className="mt-1 text-sm text-muted">Pautan log masuk dihantar ke e-mel anda. Paparan isu semasa tidak memerlukan log masuk.</p>
      {sent ? (
        <p className="mt-4 rounded-tile bg-ok/10 p-3 text-sm text-ok">Semak e-mel anda untuk pautan log masuk.</p>
      ) : (
        <form onSubmit={submit} className="mt-4 flex gap-2">
          <label className="flex flex-1 items-center gap-2 rounded-pill border border-line bg-bg px-4 py-2">
            <Mail size={14} className="text-muted" />
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="anda@contoh.com" className="w-full bg-transparent text-sm outline-none" />
          </label>
          <Button type="submit" disabled={busy}>{busy ? "…" : "Hantar"}</Button>
        </form>
      )}
    </Card>
  );
}

import { useState } from "react";
import { KeyRound, Mail } from "lucide-react";
import { supabase, errText } from "../lib/SupabaseClient";
import Button from "./ui/Button";
import Card from "./ui/Card";

/* Sign-in with the SAME account as the KKM website (it shares this Supabase project):
   email + password, or Google — the two ways that site signs people in. There is no
   sign-up here, and the e-mail link will not create an account (shouldCreateUser:false).
   Signing in is not enough to use Semasa: the account must also be on semasa_uploaders. */
export default function AuthPanel({ onToast }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const back = () => window.location.origin + window.location.pathname;

  async function withPassword(e) {
    e.preventDefault();
    setBusy(true);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) onToast(errText(error), "danger");
  }

  async function withGoogle() {
    const { error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: back() } });
    if (error) onToast(errText(error), "danger");
  }

  async function withLink() {
    if (!email) return onToast("Tulis e-mel dahulu.", "warn");
    setBusy(true);
    const { error } = await supabase.auth.signInWithOtp({
      email, options: { emailRedirectTo: back(), shouldCreateUser: false },
    });
    setBusy(false);
    if (error) onToast(errText(error), "danger"); else setSent(true);
  }

  return (
    <Card className="mx-auto max-w-md p-6">
      <h3 className="text-lg">Log masuk</h3>
      <p className="mt-1 text-sm text-muted">
        Guna akaun yang sama seperti laman web KKM. Paparan isu semasa tidak memerlukan log masuk.
      </p>
      <form onSubmit={withPassword} className="mt-4 space-y-2">
        <label className="flex items-center gap-2 rounded-pill border border-line bg-bg px-4 py-2">
          <Mail size={14} className="text-muted" />
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email"
            placeholder="anda@contoh.com" className="w-full bg-transparent text-sm outline-none" aria-label="E-mel" />
        </label>
        <label className="flex items-center gap-2 rounded-pill border border-line bg-bg px-4 py-2">
          <KeyRound size={14} className="text-muted" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password"
            placeholder="Kata laluan" className="w-full bg-transparent text-sm outline-none" aria-label="Kata laluan" />
        </label>
        <Button type="submit" className="w-full justify-center" disabled={busy || !password}>{busy ? "…" : "Log masuk"}</Button>
      </form>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="ghost" size="sm" onClick={withGoogle}>Log masuk dengan Google</Button>
        <Button variant="ghost" size="sm" onClick={withLink} disabled={busy}>Hantar pautan ke e-mel</Button>
      </div>
      {sent && <p className="mt-3 rounded-tile bg-ok/10 p-3 text-sm text-ok">Jika akaun ini wujud, pautan log masuk telah dihantar.</p>}
    </Card>
  );
}

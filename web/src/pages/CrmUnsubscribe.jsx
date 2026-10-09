import { useEffect, useState } from "react";
import { supabase } from "../lib/SupabaseClient";

/* #crm/unsub/<token>: the link under every marketing e-mail (backend/semasa/crm.py with_footer). No sign-in, no menu: the
   page calls semasa_crm_unsubscribe (supabase/031_crm.sql), which writes the moment once and answers the first name
   and the language, and says so in that language. Bahasa Malaysia first for a `bm` contact, English for `en`. */
export default function CrmUnsubscribe({ token }) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    let live = true;
    (async () => {
      const { data, error } = await supabase.rpc("semasa_crm_unsubscribe", { p_token: token });
      if (!live) return;
      setState({ loading: false, error: error?.message || "", data: data || null });
    })();
    return () => { live = false; };
  }, [token]);
  const en = state.data?.lang === "en";
  let body;
  if (state.loading) body = <p className="text-muted">…</p>;
  else if (state.error) body = <p className="text-danger">{state.error}</p>;
  else if (!state.data) body = <p>{"Pautan ini tidak dikenali. / This link is not recognised."}</p>;
  else if (en) body = <><h1 className="font-display text-2xl">You are unsubscribed{state.data.name ? `, ${state.data.name}` : ""}.</h1>
    <p className="mt-2 text-muted">{state.data.already ? "You had already unsubscribed; nothing more will be sent." : "No more marketing e-mail will come from WS Regulab Solutions. Replies to e-mails you send us still reach you."}</p></>;
  else body = <><h1 className="font-display text-2xl">Anda telah berhenti melanggan{state.data.name ? `, ${state.data.name}` : ""}.</h1>
    <p className="mt-2 text-muted">{state.data.already ? "Anda sudah berhenti melanggan sebelum ini; tiada apa lagi yang akan dihantar." : "Tiada lagi e-mel pemasaran daripada WS Regulab Solutions. Balasan kepada e-mel yang anda hantar kepada kami tetap sampai."}</p>
    <p className="mt-4 text-xs text-muted">You are unsubscribed. No more marketing e-mail will come from WS Regulab Solutions.</p></>;
  return (
    <main className="mx-auto grid min-h-screen max-w-lg place-items-center px-6 text-center">
      <div className="rounded-card border border-line bg-surface p-8 shadow-card">{body}</div>
    </main>
  );
}

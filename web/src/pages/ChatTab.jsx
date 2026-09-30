import { useEffect, useRef, useState } from "react";
import { IconBulb, IconFileText, IconPencil, IconShieldCheck } from "@tabler/icons-react";
import Ai04 from "@/components/ui/ai-04";
import { askAI, checkAI } from "../lib/chat";
import { stampMYT } from "../lib/format";
import { useLang } from "../lib/i18n";

/* AI chat: the page and the conversation, with no model behind it yet (Wan, 29 Sep 2026: "add one segment for AI
   chat, later then I will connect with API, just blank structure"). The composer is components/ui/ai-04.tsx; the one
   place a model gets plugged in is lib/chat.js `askAI`. Until then every message is kept on screen and answered with
   a plain note saying nothing is connected, never with a made-up reply. The conversation lives in this tab only and
   is gone on reload: nothing is written to the database. */
export default function ChatTab() {
  const { t } = useLang();
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  const actions = [
    { id: "caption", icon: IconPencil, label: t("Tulis kapsyen", "Write a caption"),
      prompt: t("Tulis kapsyen ws.regulab (BM) tentang: ", "Write a ws.regulab caption (Malay) about: ") },
    { id: "claim", icon: IconShieldCheck, label: t("Semak dakwaan", "Check a claim"),
      prompt: t("Semak dakwaan label ini terhadap garis panduan NPRA: ", "Check this label claim against the NPRA guidelines: ") },
    { id: "notice", icon: IconFileText, label: t("Ringkaskan notis", "Summarise a notice"),
      prompt: t("Ringkaskan notis pengawal selia ini dalam BM mudah: ", "Summarise this regulator notice in plain Malay: ") },
    { id: "idea", icon: IconBulb, label: t("Idea post", "Post ideas"),
      prompt: t("Beri tiga idea post daripada isu semasa ini: ", "Give three post ideas from this current issue: ") },
  ];

  async function send(text, { files, settings }) {
    const mine = { role: "user", text, at: new Date().toISOString(), files: files.map((f) => f.name) };
    const history = [...messages, mine];
    setMessages(history);
    setBusy(true);
    try {
      const res = await askAI(history, { files, settings });
      const reply = res.connected
        ? { role: "assistant", text: res.text, at: new Date().toISOString() }
        : { role: "note", text: t("AI belum disambungkan. Mesej anda disimpan di skrin ini sahaja.",
            "The AI is not connected yet. Your message is kept on this screen only."), at: new Date().toISOString() };
      setMessages((m) => [...m, reply]);
    } catch (e) {
      setMessages((m) => [...m, { role: "note", text: String(e?.message || e), at: new Date().toISOString() }]);
    } finally {
      setBusy(false);
    }
  }

  // "Semak model": is the model listed at Mireld, and does it really read a picture (it is asked the colour of a red square).
  async function checkModel() {
    setBusy(true);
    const r = await checkAI();
    const now = new Date().toISOString();
    let line;
    if (r.error) line = t(`Semakan gagal: ${r.error}`, `Check failed: ${r.error}`);
    else {
      const l = r.listed || {};
      const listed = !l.read ? t("senarai model tidak dapat dibaca", "the model list could not be read")
        : l.exact ? t("ada dalam senarai", "is in the list")
          : l.spelled_as ? t(`dieja "${l.spelled_as}" di sana, tukar MIRELD_MODEL`, `is spelled "${l.spelled_as}" there, set MIRELD_MODEL to that`)
            : t(`tiada dalam senarai (${(l.related || []).join(", ") || "tiada yang serupa"})`, `is not in the list (${(l.related || []).join(", ") || "nothing similar"})`);
      const im = r.image || {};
      const reads = im.reads === true ? t(`boleh baca gambar (jawab: ${im.answer})`, `reads pictures (answered: ${im.answer})`)
        : im.error ? t(`tidak baca gambar: ${im.error}`, `does not read pictures: ${im.error}`)
          : t(`tidak pasti baca gambar (jawab: ${im.answer || "-"})`, `no proof it reads pictures (answered: ${im.answer || "-"})`);
      line = `${r.model}: ${listed}; ${reads}.`;
    }
    setMessages((m) => [...m, { role: "note", text: line, at: now }]);
    setBusy(false);
  }

  const empty = messages.length === 0;
  return (
    <main className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-page flex-col px-4 pb-10 pt-10 sm:px-6">
      <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-accent">{t("Sembang AI", "AI chat")}</p>
      <button type="button" onClick={checkModel} disabled={busy}
        className="mx-auto mt-2 text-[11px] text-muted underline decoration-dotted underline-offset-2 hover:text-accent disabled:opacity-50">
        {t("Semak model dan pembaca gambar", "Check the model and its image reader")}
      </button>
      {!empty && (
        <ol className="mx-auto mt-6 w-full max-w-2xl flex-1 space-y-3" aria-live="polite">
          {messages.map((m, i) => (
            <li key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div className={
                m.role === "user" ? "max-w-[85%] whitespace-pre-wrap rounded-card bg-ink px-4 py-2.5 text-sm text-bg"
                  : m.role === "assistant" ? "max-w-[85%] whitespace-pre-wrap rounded-card border border-line bg-surface px-4 py-2.5 text-sm"
                    : "max-w-[85%] rounded-card bg-warn/10 px-4 py-2 text-xs text-warn"}>
                {m.text}
                {m.files?.length > 0 && <span className="mt-1 block text-[11px] opacity-70">📎 {m.files.join(", ")}</span>}
                <span className="mt-1 block text-[10px] opacity-60">{stampMYT(m.at)}</span>
              </div>
            </li>
          ))}
          <li ref={end} aria-hidden />
        </ol>
      )}
      <div className={empty ? "my-auto pt-10" : "sticky bottom-0 mt-6 bg-bg/90 pb-2 pt-3 backdrop-blur"}>
        <Ai04 onSubmit={send} busy={busy}
          title={empty ? t("Tanya. Semak. Terbit.", "Ask. Check. Publish.") : null}
          subtitle={empty ? t("Draf, semak dakwaan dan ringkas notis, dalam satu sembang.",
            "Draft, check claims and summarise notices in one conversation.") : null}
          placeholder={t("Tanya apa sahaja", "Ask anything")}
          actions={empty ? actions : []}
          labels={{
            attach: t("Lampirkan fail", "Attach files"), url: t("Import dari URL", "Import from URL"),
            paste: t("Tampal dari papan klip", "Paste from clipboard"), template: t("Guna templat", "Use a template"),
            soon: t("akan datang", "soon"), autoComplete: t("Auto-lengkap", "Auto-complete"),
            streaming: t("Strim jawapan", "Streaming"), showHistory: t("Tunjuk sejarah", "Show history"),
            drop: t("Lepaskan fail di sini untuk dilampirkan", "Drop files here to attach them"),
            send: t("Hantar", "Send"), add: t("Tambah lampiran", "Add attachments"),
            adjust: t("Tetapan sembang", "Chat settings"), remove: t("Buang", "Remove"),
          }} />
      </div>
    </main>
  );
}

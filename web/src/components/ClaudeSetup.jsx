import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, FlaskConical, Image as ImageIcon, Loader2, Sparkles, Wrench, XCircle } from "lucide-react";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { timeAgo } from "../lib/format";
import { formOf, rpcArgs } from "../lib/aiProviders";
import { checkAI } from "../lib/chat";
import { rateCheck } from "../lib/aiTeam";
import { CHATGPT, IMAGE_MODELS_TEST, applyPlan, claudeFacts, claudeRow, pictureTest, planState, suggestModel } from "../lib/claudeSetup";
import Card from "./ui/Card";
import Button from "./ui/Button";

/* "Claude for every text job, ChatGPT's login for pictures" (Wan, 24 Nov 2026: "fix api, I want to use claude API for all functions and
   chatgpt auth CLI for image generation, can create button so we can test new api if okay or not or live, and button to fix").
   One card, four buttons: Use this setup (writes ai_team.prefer and the pins the backend reads), Test Claude (a live question now),
   Fix (a model name typed as words becomes the id Anthropic lists), Test pictures (the ChatGPT live test: one answer, one picture
   read, one picture drawn, run by the worker; its outcome comes back in settings.ai_test_result). The key never reaches this page. */

const VERDICT = {
  ok: ["ok", "Claude menjawab", "Claude answers"],
  failing: ["bad", "Claude tidak menjawab", "Claude does not answer"],
  fixable: ["bad", "Nama model salah: Anthropic menolaknya", "The model name is wrong: Anthropic refuses it"],
  nomodel: ["bad", "Model itu tiada dalam senarai Anthropic", "That model is not in Anthropic's list"],
  keyrefused: ["bad", "Kunci ditolak", "Key refused"],
  unreachable: ["bad", "Anthropic tidak sampai", "Anthropic is unreachable"],
  nokey: ["warn", "Tiada kunci Claude", "No Claude key"],
  off: ["warn", "Claude dimatikan", "Claude is switched off"],
  unchecked: ["warn", "Belum disemak", "Not checked yet"],
  none: ["warn", "Claude belum ditambah", "Claude is not added yet"],
};
const TONE = { ok: "text-ok", bad: "text-danger", warn: "text-warn" };

export default function ClaudeSetup({ providers = [], statusRows = [], team, request, result, save, onChanged, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? 2 : 1;
  const row = useMemo(() => claudeRow(providers), [providers]);
  const status = useMemo(() => (row ? (statusRows || []).find((r) => r.slug === row.id) : null), [row, statusRows]);
  const facts = claudeFacts(row, status);
  const plan = planState(team, row);
  const [busy, setBusy] = useState("");
  const [live, setLive] = useState(null);                              // the last instant Claude test: { ok, ms, why, at }
  const [pic, setPic] = useState({ request, result });                 // the picture test's two settings, re-read while it runs
  const [now, setNow] = useState(Date.now());
  useEffect(() => setPic({ request, result }), [request, result]);
  const test = pictureTest(pic.request, pic.result, now);

  useEffect(() => {                                                    // while the picture test runs, look for its answer every 12 s
    if (test.state !== "running" || !supabase) return undefined;
    const id = setInterval(async () => {
      setNow(Date.now());
      const { data } = await supabase.from(TABLES.settings).select("key,value").in("key", ["ai_test", "ai_test_result"]);
      if (data) setPic({ request: data.find((r) => r.key === "ai_test")?.value, result: data.find((r) => r.key === "ai_test_result")?.value });
    }, 12_000);
    return () => clearInterval(id);
  }, [test.state]);

  const canSave = typeof save === "function";
  const model = facts.needsFix ? facts.fixedTo : (row?.model || "");

  // Fix: the saved model becomes an id Anthropic lists (the typed name when it already matches one, else the best Claude listed)
  async function fixModel() {
    if (!row) return null;
    const target = facts.needsFix ? facts.fixedTo : suggestModel(facts.listed);
    if (!target) { onToast?.(t("Tiada model Claude dalam senarai Anthropic lagi: tunggu semakan API seterusnya.", "No Claude model in Anthropic's list yet: wait for the next API check."), "warn"); return null; }
    const { error } = await supabase.rpc("semasa_save_ai_provider", rpcArgs({ ...formOf(row), model: target }));
    if (error) throw new Error(errText(error));
    await onChanged?.();
    return target;
  }

  async function run(name, fn) {
    setBusy(name);
    try { await fn(); } catch (e) { onToast?.(e?.message || String(e), "danger"); } finally { setBusy(""); }
  }

  const testClaude = (modelId) => run("test", async () => {
    const m = modelId || model;
    const r = rateCheck(await checkAI(`${row.id}|${m}`));
    setLive({ ok: !!(r.tested && r.parts?.answered), reads: !!r.parts?.picture, ms: r.ms, why: r.why || r.note || "", model: m, at: new Date().toISOString() });
    if (canSave) save("ai_team", { ...(team || {}), changed_at: new Date().toISOString() }).catch(() => {});      // the worker asks it too (supabase/057)
  });
  const fixClaude = () => run("fix", async () => {
    const m = await fixModel();
    if (m) { onToast?.(t("Model dibetulkan kepada {m}. Menguji sekarang…", "Model corrected to {m}. Testing now…", { m }), "ok"); await testClaude(m); }
  });
  const usePlan = () => run("plan", async () => {
    let m = model;
    if (facts.needsFix) m = (await fixModel()) || m;
    await save("ai_team", applyPlan(team, row, m));
    onToast?.(t("Disimpan: Claude untuk semua teks, ChatGPT untuk gambar. Pengarah mengesahkan dalam kira-kira seminit (jika Claude rosak, robot lain masih menjawab).",
      "Saved: Claude for all text, ChatGPT for pictures. The router confirms in about a minute (if Claude is down, the other robots still answer)."), "ok");
  });
  const testPictures = () => run("pic", async () => {
    const at = new Date().toISOString();
    await save("ai_test", { at, what: CHATGPT });
    setPic((p) => ({ ...p, request: { at, what: CHATGPT } }));
    setNow(Date.now());
    onToast?.(t("Ujian bermula: ChatGPT menjawab, membaca dan melukis satu gambar. Keputusan dalam kira-kira 3 minit.", "Test started: ChatGPT answers, reads and draws one picture. The result shows in about 3 minutes."), "ok");
  });
  const findModels = () => run("picmodels", async () => {
    const at = new Date().toISOString();
    await save("ai_test", { at, what: IMAGE_MODELS_TEST });
    setPic((p) => ({ ...p, request: { at, what: IMAGE_MODELS_TEST } }));
    setNow(Date.now());
    onToast?.(t("Mencari model gambar ChatGPT: satu hingga lima gambar ujian dilukis. Keputusan dalam beberapa minit.", "Looking for ChatGPT's picture models: one to five test pictures are drawn. The result shows in a few minutes."), "ok");
  });
  const fixPictures = () => run("picfix", async () => {
    const pins = { ...(team?.pins || {}), image_gen: { gateway: CHATGPT, model: "" } };
    await save("ai_team", { ...(team || {}), pins, changed_at: new Date().toISOString() });
    onToast?.(t("Gambar dipasang semula pada ChatGPT. Tekan Uji gambar.", "Pictures pinned to ChatGPT again. Press Test pictures."), "ok");
  });

  const [tone, bm, en] = VERDICT[facts.verdict] || VERDICT.none;
  const Dot = ({ ok, bad }) => (ok ? <CheckCircle2 size={14} className="text-ok" /> : bad ? <XCircle size={14} className="text-danger" /> : <span className="inline-block h-2 w-2 rounded-full bg-warn" />);

  return (
    <Card className="space-y-3 p-4" data-claude-setup>
      <div>
        <h3 className="flex items-center gap-2 text-lg"><Sparkles size={16} className="text-accent" /> {t("Claude untuk semua fungsi, ChatGPT untuk gambar", "Claude for every function, ChatGPT for pictures")}</h3>
        <p className="mt-1 max-w-2xl text-[12px] text-muted">{t(
          "Satu tekan memasang Claude (kunci Anthropic anda) sebagai penulis dan pembaca untuk semua kerja teks, dan log masuk ChatGPT untuk melukis. Jika satu rosak, robot lain masih menjawab, supaya tiada kerja berhenti.",
          "One press sets Claude (your Anthropic key) as the writer and reader for every text job, and your ChatGPT login for drawing. If one is down the other robots still answer, so no job stops.")}</p>
      </div>

      <section className="rounded-card border border-line p-3" data-claude-box>
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <Dot ok={tone === "ok"} bad={tone === "bad"} />
          <span className={TONE[tone]}>{[bm, en][L - 1]}</span>
          {row && <span className="text-[11px] font-normal text-muted">· {row.name || row.id} · {t("model disimpan", "saved model")}: <code>{facts.saved || "-"}</code></span>}
        </p>
        {facts.verdict === "fixable" && <p className="mt-1 text-[11px] text-muted">{t("Anthropic memanggilnya", "Anthropic calls it")} <code>{facts.fixedTo}</code>. {t("Tekan Betulkan: nama disimpan semula dan diuji.", "Press Fix: the name is saved again and tested.")}</p>}
        {facts.error && facts.verdict !== "ok" && <p className="mt-1 break-words text-[11px] text-muted">{facts.error.slice(0, 200)}</p>}
        {live && (
          <p className={`mt-1 text-[11px] ${live.ok ? "text-ok" : "text-danger"}`} data-claude-live>
            {live.ok ? t("Diuji sekarang: {m} menjawab dalam {s} s dan {p}.", "Live test: {m} answered in {s} s and {p}.", { m: live.model, s: live.ms ? (live.ms / 1000).toFixed(1) : "?",
              p: live.reads ? t("membaca gambar ujian", "read the test picture") : t("TIDAK membaca gambar ujian", "did NOT read the test picture") })
              : t("Diuji sekarang: {m} tidak menjawab: {w}", "Live test: {m} did not answer: {w}", { m: live.model, w: live.why || "-" })}
            <span className="text-muted"> · {timeAgo(live.at, now)}</span>
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" variant="soft" disabled={!row || !!busy || facts.verdict === "nokey"} onClick={() => testClaude()} data-claude-test>
            {busy === "test" ? <Loader2 size={13} className="animate-spin" /> : <FlaskConical size={13} />} {t("Uji Claude sekarang", "Test Claude now")}
          </Button>
          <Button size="sm" variant={facts.verdict === "fixable" || facts.verdict === "nomodel" ? "primary" : "ghost"} disabled={!row || !!busy || !["fixable", "nomodel", "failing"].includes(facts.verdict)} onClick={fixClaude} data-claude-fix>
            {busy === "fix" ? <Loader2 size={13} className="animate-spin" /> : <Wrench size={13} />} {t("Betulkan", "Fix")}
          </Button>
        </div>
      </section>

      <section className="rounded-card border border-line p-3" data-pictures-box>
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <ImageIcon size={14} className="text-accent" /> {t("Gambar melalui ChatGPT (log masuk anda)", "Pictures through ChatGPT (your login)")}
          <span className={`text-[11px] font-normal ${plan.pictures ? "text-ok" : "text-muted"}`}>· {plan.pictures ? t("dipasang", "set") : t("belum dipasang", "not set")}</span>
        </p>
        {test.state === "running" && <p className="mt-1 flex items-center gap-1 text-[11px] text-accent" data-pictures-running><Loader2 size={11} className="animate-spin" />{t("ChatGPT sedang diuji (menjawab, membaca, melukis)…", "ChatGPT is being tested (answer, read, draw)…")}</p>}
        {test.state === "lost" && <p className="mt-1 text-[11px] text-warn">{t("Tiada jawapan selepas 12 minit: ujian mungkin tidak bermula. Tekan Uji gambar lagi, atau jalankan “ChatGPT live test” di GitHub Actions.", "No answer after 12 minutes: the test may not have started. Press Test pictures again, or run “ChatGPT live test” in GitHub Actions.")}</p>}
        {test.state === "ok" && <p className="mt-1 text-[11px] text-ok" data-pictures-ok>{t("Lulus: ChatGPT menjawab, membaca dan melukis satu gambar dengan {m}.", "Passed: ChatGPT answered, read and drew one picture with {m}.", { m: test.model || "-" })} <span className="text-muted">· {timeAgo(test.at, now)}</span></p>}
        {test.state === "ignored" && <p className="mt-1 text-[11px] text-muted" data-pictures-ignored>{t("Model gambar tidak boleh dipilih dengan log masuk ChatGPT: ChatGPT melukis walaupun nama model gambar yang tidak wujud diberi, jadi ia memilih model gambarnya sendiri. Sebab itu tiada gpt-image-2 dalam senarai.", "A picture model cannot be chosen with a ChatGPT login: ChatGPT drew even when given a picture model that does not exist, so it picks its own. That is why no gpt-image-2 is listed.")} <span className="opacity-70">· {timeAgo(test.at, now)}</span></p>}
        {test.state === "models" && <p className="mt-1 text-[11px] text-ok" data-pictures-models>{t("Model gambar yang dilukis oleh log masuk ini:", "Picture models this login draws with:")} {test.models.join(", ")} <span className="text-muted">· {timeAgo(test.at, now)}</span></p>}
        {test.state === "nomodels" && <p className="mt-1 text-[11px] text-muted">{t("Tiada model gambar yang dinamakan diterima: ChatGPT melukis dengan model lalainya.", "No named picture model was accepted: ChatGPT draws with its default.")}</p>}
        {test.state === "notconnected" && <p className="mt-1 text-[11px] text-danger">{t("ChatGPT belum log masuk: log masuk di kad ChatGPT di bawah, kemudian uji lagi.", "ChatGPT is not logged in: log in on the ChatGPT card below, then test again.")}</p>}
        {test.state === "failed" && (
          <p className="mt-1 text-[11px] text-danger" data-pictures-failed>
            {test.bad.map((b) => `${b.step}: ${b.detail}`).join(" · ") || t("Gagal", "Failed")} <span className="text-muted">· {timeAgo(test.at, now)}</span>
            {test.bad.some((b) => /402|payment|limit|quota/i.test(b.detail)) && <span className="block text-muted">{t("402 bermaksud akaun ChatGPT kehabisan peruntukan gambar: tunggu ia ditetapkan semula, atau sistem terus menggunakan pelukis lain.", "A 402 means the ChatGPT account has used its picture allowance: wait for the reset, or the system keeps drawing with the other makers.")}</span>}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" variant="soft" disabled={!canSave || !!busy || test.state === "running"} onClick={testPictures} data-pictures-test
            title={t("Melukis satu gambar sebenar: menggunakan satu peruntukan gambar ChatGPT", "Draws one real picture: uses one ChatGPT picture allowance")}>
            {busy === "pic" ? <Loader2 size={13} className="animate-spin" /> : <FlaskConical size={13} />} {t("Uji gambar", "Test pictures")}
          </Button>
          <Button size="sm" variant="ghost" disabled={!canSave || !!busy || test.state === "running"} onClick={findModels} data-pictures-models-find
            title={t("Bertanya kepada ChatGPT model gambar mana yang ia lukis (melukis 1 hingga 5 gambar ujian)", "Asks ChatGPT which picture models it draws with (draws 1 to 5 test pictures)")}>
            {busy === "picmodels" ? <Loader2 size={13} className="animate-spin" /> : <ImageIcon size={13} />} {t("Cari model gambar", "Find picture models")}
          </Button>
          <Button size="sm" variant={!plan.pictures ? "primary" : "ghost"} disabled={!canSave || !!busy} onClick={fixPictures} data-pictures-fix>
            {busy === "picfix" ? <Loader2 size={13} className="animate-spin" /> : <Wrench size={13} />} {t("Betulkan", "Fix")}
          </Button>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" disabled={!row || !canSave || !!busy || ["nokey", "none"].includes(facts.verdict)} onClick={usePlan} data-plan-apply>
          {busy === "plan" ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {t("Guna tetapan ini", "Use this setup")}
        </Button>
        <span className={`text-[11px] ${plan.text && plan.pictures ? "text-ok" : "text-muted"}`} data-plan-state>
          {plan.text && plan.pictures && plan.reads ? t("Aktif: Claude menulis semua teks dan membaca gambar, ChatGPT melukis.", "Active: Claude writes all text and reads pictures, ChatGPT draws.")
            : plan.text && plan.pictures ? t("Claude menulis dan ChatGPT melukis; tekan Guna tetapan ini supaya Claude juga membaca gambar.", "Claude writes and ChatGPT draws; press Use this setup so Claude reads pictures too.")
            : t("Belum aktif sepenuhnya.", "Not fully active yet.")}
        </span>
      </div>
    </Card>
  );
}

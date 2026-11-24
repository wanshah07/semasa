import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, HelpCircle, Hourglass, KeyRound, Loader2, PenLine, RefreshCw, XCircle } from "lucide-react";
import { fadeUp } from "../design/motion";
import { TABLES, errText, supabase } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { timeAgo } from "../lib/format";
import { ACCOUNT_KEY_SLUGS, CARDS, accountKeyProblem, amountOf, countdownOf, countdownText, isoToMytInput, manualEntry, mytText, viewOf } from "../lib/credit";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { Input, Label } from "../components/ui/Field";

/* Baki kredit API (Wan, 23 Nov 2026: "satu segment untuk pantau berapa banyak realtime baki credit API tinggal dan validity for
   mireld, rootsys dan KioskAPI"). One card a gateway: what is left, until when, and how fresh the reading is. The readings are
   semasa_api_status.balance.credit, written every 15 minutes by .github/workflows/api-credit.yml (backend/semasa/api_credit.py);
   this page re-reads the table every 30 seconds and "Refresh now" asks for a run (settings.credit_check, supabase/092).
   A gateway whose balance the API cannot be asked yet says so, and lists every path tried and what it answered (key names only),
   so the right endpoint can be found. A figure Wan types from the gateway's own dashboard is labelled MANUAL with its date and is
   never mixed into a live reading. The page holds no key. */

const BADGE = {
  ok: { cls: "bg-ok/15 text-ok", bar: "bg-ok", icon: CheckCircle2, bm: "OK", en: "OK" },
  low: { cls: "bg-warn/15 text-warn", bar: "bg-warn", icon: AlertTriangle, bm: "Rendah", en: "Low" },
  expired: { cls: "bg-danger/15 text-danger", bar: "bg-danger", icon: XCircle, bm: "Tamat", en: "Expired" },
  unknown: { cls: "bg-surface-2 text-muted", bar: "bg-muted", icon: HelpCircle, bm: "Tidak diketahui", en: "Unknown" },
};
const WAIT_MS = 4 * 60_000;           // how long "Refresh now" waits for the run to land before it stops watching

export default function CreditTab({ settings, save, onToast }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? "en" : "bm";
  // the probe writes these rows (every 15 minutes here, the 6-hourly probe, the 5-minute pulse); read them every 30 seconds
  const statusT = useTable(TABLES.apiStatus, { enabled: true, select: "slug,name,role,base_url,key_set,key_ok,reachable,checked_at,balance",
    order: "slug", ascending: true, limit: 30, realtime: true, everyMs: 30_000 });
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), 15_000); return () => clearInterval(id); }, []);
  const manual = settings?.api_credit_manual && typeof settings.api_credit_manual === "object" ? settings.api_credit_manual : {};
  const views = useMemo(() => CARDS.map((c) => ({ card: c, v: viewOf(statusT.rows.find((r) => r.slug === c.slug), manual[c.slug], now) })),
    [statusT.rows, manual, now]);
  const lastRead = views.reduce((m, { v }) => (v.readAt && v.readAt > m ? v.readAt : m), "");

  // "Refresh now": write settings.credit_check; the database wakes the workflow; the cards redraw as the run lands
  const [asked, setAsked] = useState(0);                       // when it was asked (ms), 0 = not waiting
  const [busy, setBusy] = useState(false);
  const landed = asked && views.some(({ v }) => v.attemptAt && Date.parse(v.attemptAt) >= asked - 5000);
  const reload = useRef(null);
  reload.current = statusT.reload;
  useEffect(() => {
    if (!asked) return undefined;
    if (landed || Date.now() - asked > WAIT_MS) { setAsked(0); return undefined; }
    const id = setInterval(() => { reload.current?.(); setNow(Date.now()); }, 8000);
    return () => clearInterval(id);
  }, [asked, landed, now]);
  const refresh = async () => {
    if (typeof save !== "function") return;
    setBusy(true);
    try {
      await save("credit_check", { requested_at: new Date().toISOString() });
      setAsked(Date.now());
      onToast?.(t("Diminta: bacaan baharu tiba dalam kira-kira satu minit.", "Asked: a new reading lands in about a minute."), "ok");
    } catch (e) {
      const msg = String(e?.message || e);
      onToast?.(/not found|0 rows/.test(msg) ? t("Jalankan supabase/092_api_credit.sql sekali dahulu, atau tunggu larian 15 minit.", "Run supabase/092_api_credit.sql once first, or wait for the 15-minute run.") : msg, "danger");
    } finally { setBusy(false); }
  };
  // The account key that reads a gateway's balance (supabase/096; Wan, 24 Nov 2026: "add key directly in the semasa so can read
  // balance"). The page sends the token once and never gets it back: it sees the user id and the token's last four characters.
  const [accounts, setAccounts] = useState([]);
  const [noAccounts, setNoAccounts] = useState(false);          // 096 not run yet
  const loadAccounts = async () => {
    if (!supabase) return;
    const { data, error } = await supabase.rpc("semasa_credit_accounts_status");
    if (error) { setNoAccounts(/semasa_credit_accounts_status|PGRST202|42883|does not exist/i.test(`${error.code} ${error.message}`)); return; }
    setNoAccounts(false);
    setAccounts(Array.isArray(data) ? data : []);
  };
  useEffect(() => { loadAccounts(); }, []);
  const saveAccount = async (slug, token, userId) => {
    const { data, error } = await supabase.rpc("semasa_credit_account_save", { p_slug: slug, p_access_token: token, p_user_id: userId });
    if (error) { onToast?.(errText(error), "danger"); return false; }
    setAccounts(Array.isArray(data) ? data : []);
    onToast?.(t("Kunci akaun disimpan. Baki dibaca sekarang.", "Account key saved. The balance is being read now."), "ok");
    refresh();                                                    // the reading with the new key lands in about a minute
    return true;
  };
  const removeAccount = async (slug) => {
    const { data, error } = await supabase.rpc("semasa_credit_account_remove", { p_slug: slug });
    if (error) { onToast?.(errText(error), "danger"); return false; }
    setAccounts(Array.isArray(data) ? data : []);
    onToast?.(t("Kunci akaun dibuang.", "Account key removed."), "ok");
    return true;
  };
  const saveManual = async (slug, entry) => {
    const next = { ...manual };
    if (entry) next[slug] = entry; else delete next[slug];
    try {
      await save("api_credit_manual", next);
      onToast?.(entry ? t("Angka taipan disimpan (ditanda MANUAL).", "Typed figure saved (marked MANUAL).") : t("Angka taipan dibuang.", "Typed figure removed."), "ok");
      return true;
    } catch (e) {
      const msg = String(e?.message || e);
      onToast?.(/not found|0 rows/.test(msg) ? t("Jalankan supabase/092_api_credit.sql sekali untuk menyimpan angka taipan.", "Run supabase/092_api_credit.sql once to save a typed figure.") : msg, "danger");
      return false;
    }
  };
  const missing = /semasa_api_status/.test(statusT.error || "");

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-10 sm:px-6" data-credit-page>
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">{t("Baki kredit API", "API credit")}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">{t("Berapa kredit yang tinggal dan sehingga bila ia sah, untuk Mireld, rootsys dan KiosAPI. Dibaca setiap 15 minit daripada API setiap gerbang dengan kuncinya sendiri; halaman ini menyemak semula setiap 30 saat.",
            "How much credit is left and until when it is valid, for Mireld, rootsys and KiosAPI. Read every 15 minutes from each gateway's own API with its own key; this page re-reads every 30 seconds.")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {lastRead && <span className="text-xs text-muted" data-credit-last><RefreshCw size={12} className="mr-1 inline" />{t("dibaca", "read")} {timeAgo(lastRead, now)}</span>}
          <Button type="button" size="sm" variant="ghost" onClick={refresh} disabled={busy || !!asked} data-credit-refresh>
            {busy || asked ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} {asked ? t("Menunggu bacaan…", "Waiting for the reading…") : t("Segarkan sekarang", "Refresh now")}
          </Button>
        </div>
      </motion.div>

      {missing && <p className="mb-4 rounded-tile bg-warn/10 p-3 text-sm text-warn">{t("Jadual belum ada: jalankan supabase/035_repos_api.sql sekali.", "The table is not there yet: run supabase/035_repos_api.sql once.")}</p>}
      {statusT.error && !missing && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{statusT.error}</p>}

      <div className="grid gap-4 lg:grid-cols-3">
        {views.map(({ card, v }) => <CreditCard key={card.slug} card={card} v={v} now={now} L={L} t={t} onSaveManual={saveManual} loading={statusT.loading} canSave={typeof save === "function"}
          account={accounts.find((a) => a.slug === card.slug) || null} noAccounts={noAccounts} onSaveAccount={saveAccount} onRemoveAccount={removeAccount} />)}
      </div>

      <p className="mt-6 max-w-3xl text-[11px] text-muted">{t("Unit kredit: setiap gerbang mengira dengan unitnya sendiri. API Mireld memberi 89.11 manakala papan pemuka Mireld menunjukkan 89.11M (sejuta kali ganda; jumlah pelan 1275 lawan 1.27B): kedua-duanya dipaparkan. rootsys dibaca daripada /v1/quota (token). Baki KiosAPI ada pada akaun, yang tidak boleh dibaca dengan kunci API: letak rahsia KIOSAPI_ACCESS_TOKEN dan KIOSAPI_USER_ID (token akses dari Tetapan peribadi › Keselamatan) di GitHub; sehingga itu kad menunjukkan setiap laluan yang dicuba.",
        "Credit units: each gateway counts in its own unit. Mireld's API says 89.11 while its dashboard shows 89.11M (a million times that; plan total 1275 against 1.27B): both are shown. rootsys is read from /v1/quota (tokens). KiosAPI's balance sits on the account, which an API key cannot read: add the secrets KIOSAPI_ACCESS_TOKEN and KIOSAPI_USER_ID (the access token comes from Personal settings › Security) in GitHub; until then the card lists every path tried.")}</p>
    </main>
  );
}

function CreditCard({ card, v, now, L, t, onSaveManual, loading, canSave, account, noAccounts, onSaveAccount, onRemoveAccount }) {
  const B = BADGE[v.status] || BADGE.unknown;
  const f = v.figure;
  const left = f ? amountOf(f.remaining, f) : null;
  const total = f ? amountOf(f.total, f) : null;
  const used = f ? amountOf(f.used, f) : null;
  const pctLeft = f && Number.isFinite(Number(f.percent_left)) && f.percent_left !== null ? Number(f.percent_left) : null;
  const cd = v.expiresAt ? countdownOf(v.expiresAt, now) : null;
  return (
    <Card className="flex flex-col p-4" data-credit-card={card.slug} data-credit-status={v.status}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-display text-lg">{card.name}</p>
          <p className="truncate text-xs text-muted">{card.host}</p>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-pill px-2 py-0.5 text-[11px] ${B.cls}`} data-credit-badge><B.icon size={12} /> {B[L]}</span>
      </div>

      {/* what is left */}
      <div className="mt-4">
        <p className="text-[11px] font-medium text-muted">{t("Baki kredit", "Credit left")}
          {v.source === "manual" && <span className="ml-2 rounded-pill bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent" data-credit-manual-badge>MANUAL</span>}
        </p>
        {left?.text ? (
          <>
            <p className="font-display text-3xl tabular-nums" data-credit-left>{left.text}</p>
            {left.scaled && <p className="text-[11px] text-muted" data-credit-raw>{t("API:", "API:")} {left.raw} · {t("unit kredit; papan pemuka gerbang mengira sejuta kali ganda", "credit units; the gateway's dashboard counts a million times this")}</p>}
            {pctLeft !== null && (
              <div className="mt-2" data-credit-bar>
                <div className="h-2 rounded-pill bg-surface-2" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pctLeft} aria-label={t("Peratus tinggal", "Percent left")}>
                  <div className={`h-2 rounded-pill ${B.bar}`} style={{ width: `${Math.max(pctLeft > 0 ? 2 : 0, pctLeft)}%` }} />
                </div>
                <p className="mt-1 flex justify-between text-[11px] text-muted"><span>{pctLeft}% {t("tinggal", "left")}</span>
                  {total?.text && <span>{used?.text ? `${used.text} ${t("terpakai", "used")} · ` : ""}{total.text} {t("jumlah", "total")}</span>}</p>
              </div>
            )}
            {pctLeft === null && total?.text && <p className="mt-1 text-[11px] text-muted">{total.text} {t("jumlah", "total")}</p>}
          </>
        ) : (
          <p className="text-sm text-muted" data-credit-none>{!v.hasRow ? t("Belum disemak: larian API menulis kad ini selepas bacaan pertama.", "Not checked yet: the API run writes this card after its first reading.")
            : !v.keySet ? t("Tiada kunci untuk gerbang ini dalam konfigurasi pekerja.", "No key for this gateway in the workers' configuration.")
              : v.keyInfo?.unlimited
                ? t("Kunci ini tiada had sendiri, jadi ia tidak membawa baki. Baki tambah nilai berada pada AKAUN: tambah dua rahsia di bawah untuk membacanya.",
                  "This key has no limit of its own, so it carries no balance. The top-up balance sits on the ACCOUNT: add the two secrets below to read it.")
                : t("Tiada titik akhir baki menjawab untuk kunci ini lagi.", "No balance endpoint answers for this key yet.")}</p>
        )}
        {v.source === "manual" && <p className="mt-1 text-[11px] text-muted" data-credit-manual-note>{t("Angka ini ditaip oleh Wan daripada papan pemuka gerbang pada", "Typed by Wan from the gateway's own dashboard on")} {mytText(v.manualAt, L)}{v.manual?.note ? ` · ${v.manual.note}` : ""}. {t("Ia bukan bacaan langsung.", "It is not a live reading.")}</p>}
      </div>

      {/* validity */}
      <div className="mt-4 rounded-tile bg-surface-2/60 p-3" data-credit-validity>
        <p className="flex items-center gap-1 text-[11px] font-medium text-muted"><Hourglass size={12} /> {t("Sah sehingga", "Valid until")}
          {v.expiryManual && <span className="ml-1 rounded-pill bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">MANUAL</span>}</p>
        {v.expiresAt ? (
          <>
            <p className="text-sm font-medium" data-credit-expiry>{mytText(v.expiresAt, L)}</p>
            <p className={`text-sm tabular-nums ${cd?.past ? "text-danger" : v.status === "low" ? "text-warn" : "text-ink"}`} data-credit-countdown>{countdownText(cd, t)}</p>
          </>
        ) : v.keyInfo?.neverExpires
          ? <p className="text-sm text-muted" data-credit-key-forever>{t("Kunci ini tiada tarikh tamat. (Tambah nilai akaun mungkin ada.)", "This key has no end date. (The account's top-up may have one.)")}</p>
          : <p className="text-sm text-muted">{t("Tarikh tamat tidak dibaca daripada API.", "No expiry date is readable from the API.")}</p>}
        {v.keyInfo && v.source === "none" && v.keyInfo.used !== null && (
          <p className="mt-1 text-[11px] text-muted" data-credit-key-used>{t("Dibelanjakan dengan kunci ini setakat ini:", "Spent with this key so far:")} <b className="text-ink">US$ {v.keyInfo.used.toFixed(2)}</b></p>
        )}
      </div>

      {/* freshness and where it came from */}
      <div className="mt-3 space-y-0.5 text-[11px] text-muted">
        {v.readAt ? <p data-credit-age>{t("Disemak", "Last checked")} {timeAgo(v.readAt, now)}{v.late && <span className="text-warn"> · {t("terlewat: larian 15 minit tidak datang", "late: the 15-minute run is behind")}</span>}</p>
          : !loading && <p>{t("Belum pernah dibaca.", "Never read yet.")}</p>}
        {v.stale && <p className="text-warn" data-credit-stale>{t("Gerbang tidak dapat dihubungi; ini bacaan baik yang terakhir.", "The gateway could not be reached; this is the last good reading.")}</p>}
        {v.endpoint && <p data-credit-endpoint>{t("Titik akhir:", "Endpoint:")} <code className="rounded bg-surface-2 px-1">{v.endpoint}</code></p>}
      </div>

      {/* what each path answered: how the right endpoint is found for a gateway with no readable balance */}
      {v.tried.length > 0 && (
        <details className="mt-3 text-xs" open={v.source === "none" && v.hasRow} data-credit-tried>
          <summary className="cursor-pointer text-muted hover:text-ink">{t("Laluan dicuba", "Paths tried")} · {v.tried.length}</summary>
          <ul className="mt-2 max-h-64 space-y-1.5 overflow-y-auto pr-1">
            {v.tried.map((p, i) => (
              <li key={`${p.path}-${i}`} className="rounded-tile bg-surface-2/60 p-2">
                <p className="flex flex-wrap items-center gap-x-2"><code className="break-all">{p.path}</code>
                  <span className={p.http === 200 ? "text-ok" : "text-muted"}>{p.http ?? t("tiada jawapan", "no answer")}</span>
                  <span className="text-muted">{p.shape}</span>{p.read && <span className="text-ok">{t("dibaca", "read")}</span>}</p>
                {p.keys?.length > 0 && <p className="mt-0.5 break-words text-[11px] text-muted">{t("kunci:", "keys:")} {p.keys.join(", ")}</p>}
              </li>
            ))}
          </ul>
          <p className="mt-1 text-[11px] text-muted">{t("Hanya nama kunci JSON; tiada nilai disimpan.", "JSON key names only; no value is stored.")}</p>
        </details>
      )}

      {(ACCOUNT_KEY_SLUGS.includes(card.slug) || account) && (
        <AccountKey card={card} v={v} t={t} L={L} account={account} missing={noAccounts} onSave={onSaveAccount} onRemove={onRemoveAccount} />
      )}
      <Manual card={card} v={v} t={t} L={L} onSave={onSaveManual} canSave={canSave} />
    </Card>
  );
}

/* The account key that reads the balance (supabase/096). KiosAPI's top-up sits on the ACCOUNT, which the API key cannot read: the
   panel's access token (Personal settings, Security) plus the user id can. Typed here once; only the worker reads it back, and
   it is sent only to that gateway. An access token can manage the account, so Remove is always one tap away. */
function AccountKey({ card, v, t, L, account, missing, onSave, onRemove }) {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [userId, setUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const [sure, setSure] = useState(false);
  const problem = accountKeyProblem(token, userId);
  const submit = async (e) => {
    e.preventDefault();
    if (problem) return;
    setBusy(true);
    if (await onSave(card.slug, token.trim(), userId.trim())) { setToken(""); setUserId(""); setOpen(false); }   // the token leaves the page once saved
    setBusy(false);
  };
  const remove = async () => {
    if (!sure) { setSure(true); setTimeout(() => setSure(false), 6000); return; }
    setBusy(true);
    await onRemove(card.slug);
    setBusy(false); setSure(false);
  };
  if (missing) return <p className="mt-3 border-t border-line pt-3 text-[11px] text-muted" data-credit-account={card.slug}>{t("Jalankan supabase/096_credit_account_keys.sql sekali untuk menaip kunci akaun di sini.", "Run supabase/096_credit_account_keys.sql once to type the account key here.")}</p>;
  return (
    <div className="mt-3 border-t border-line pt-3" data-credit-account={card.slug}>
      <p className="flex items-center gap-1 text-xs font-medium"><KeyRound size={12} className="text-accent" /> {t("Kunci akaun (untuk membaca baki)", "Account key (to read the balance)")}</p>
      {account ? (
        <p className="mt-1 text-[11px] text-muted" data-credit-account-saved>
          {t("Disimpan", "Saved")}: …{account.token_hint} · {t("ID pengguna", "user id")} {account.user_id} · {mytText(account.updated_at, L)}
          {v.source !== "live" && <span className="block text-warn">{t("Baki belum dibaca dengan kunci ini: semak token dan ID, kemudian Segar semula.", "The balance has not been read with this key yet: check the token and the id, then Refresh.")}</span>}
        </p>
      ) : (
        <p className="mt-1 text-[11px] text-muted">{t("Di panel {n}: Tetapan peribadi → Keselamatan → jana Token Akses, dan salin ID pengguna (nombor). Tampal kedua-duanya di sini.",
          "In the {n} panel: Personal settings → Security → generate an Access Token, and copy your user ID (a number). Paste both here.", { n: card.name })}</p>
      )}
      {!open ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="soft" onClick={() => setOpen(true)} data-credit-account-open>{account ? t("Tukar kunci", "Change the key") : t("Tambah kunci akaun", "Add the account key")}</Button>
          {account && <Button type="button" size="sm" variant={sure ? "danger" : "ghost"} disabled={busy} onClick={remove} data-credit-account-remove>{sure ? t("Tekan lagi untuk buang", "Tap again to remove") : t("Buang", "Remove")}</Button>}
        </div>
      ) : (
        <form onSubmit={submit} className="mt-2 space-y-2">
          <label className="block"><Label>{t("Token akses", "Access token")}</Label><Input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} data-credit-account-token /></label>
          <label className="block"><Label>{t("ID pengguna (nombor)", "User ID (a number)")}</Label><Input inputMode="numeric" value={userId} onChange={(e) => setUserId(e.target.value)} data-credit-account-user /></label>
          {(token || userId) && problem && <p className="text-[11px] text-warn">{problem[L === "en" ? 1 : 0]}</p>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={!!problem || busy}>{busy ? <Loader2 size={13} className="animate-spin" /> : null} {t("Simpan", "Save")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => { setOpen(false); setToken(""); setUserId(""); }}>{t("Batal", "Cancel")}</Button>
          </div>
          <p className="text-[11px] text-muted">{t("Token dihantar sekali dan tidak dipaparkan semula. Ia hanya dihantar ke {h}.", "The token is sent once and never shown again. It is only ever sent to {h}.", { h: card.host })}</p>
        </form>
      )}
    </div>
  );
}

/* Wan can type the figure his gateway's own dashboard shows, for a gateway whose API cannot be asked. It is kept in
   settings.api_credit_manual with the day it was typed, drawn with a MANUAL badge, and a live reading always replaces it. */
function Manual({ card, v, t, L, onSave, canSave }) {
  const m = v.manual;
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ remaining: "", total: "", unit: card.unit, expires: "", note: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) setForm({ remaining: m?.remaining != null ? String(m.remaining) : "", total: m?.total != null ? String(m.total) : "", unit: m?.unit || card.unit,
      expires: isoToMytInput(m?.expires_at), note: m?.note || "" });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const entry = manualEntry(form);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    if (!entry) return;
    setBusy(true);
    if (await onSave(card.slug, entry)) setOpen(false);
    setBusy(false);
  };
  return (
    <div className="mt-3 border-t border-line pt-3" data-credit-manual={card.slug}>
      {!open ? (
        <button type="button" onClick={() => setOpen(true)} disabled={!canSave} className="inline-flex items-center gap-1 text-xs text-muted underline hover:text-accent disabled:opacity-50">
          <PenLine size={12} /> {m ? t("Ubah angka taipan", "Edit the typed figure") : t("Taip angka daripada papan pemuka gerbang", "Type the figure from the gateway's dashboard")}
        </button>
      ) : (
        <form onSubmit={submit} className="space-y-2">
          <p className="text-[11px] text-muted">{t("Disimpan dengan tarikh hari ini dan ditanda MANUAL. Bacaan langsung sentiasa menggantikannya.", "Saved with today's date and marked MANUAL. A live reading always replaces it.")}</p>
          <div className="grid grid-cols-2 gap-2">
            <label><Label>{t("Baki", "Left")}</Label><Input value={form.remaining} onChange={set("remaining")} placeholder={card.slug === "kiosapi" ? "Rp 8.817" : "545.1M"} inputMode="decimal" /></label>
            <label><Label>{t("Jumlah (pilihan)", "Total (optional)")}</Label><Input value={form.total} onChange={set("total")} placeholder={card.slug === "kiosapi" ? "" : "2.575B"} inputMode="decimal" /></label>
            <label><Label>{t("Unit", "Unit")}</Label><Input value={form.unit} onChange={set("unit")} /></label>
            <label><Label hint="MYT">{t("Sah sehingga", "Valid until")}</Label><Input type="datetime-local" value={form.expires} onChange={set("expires")} /></label>
          </div>
          <label className="block"><Label>{t("Catatan (pilihan)", "Note (optional)")}</Label><Input value={form.note} onChange={set("note")} maxLength={160} /></label>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={!entry || busy}>{busy ? <Loader2 size={13} className="animate-spin" /> : null} {t("Simpan", "Save")}</Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>{t("Batal", "Cancel")}</Button>
            {m && <Button type="button" size="sm" variant="danger" disabled={busy} onClick={async () => { setBusy(true); if (await onSave(card.slug, null)) setOpen(false); setBusy(false); }}>{t("Buang", "Remove")}</Button>}
          </div>
        </form>
      )}
      {!open && m && v.source !== "manual" && <p className="mt-1 text-[11px] text-muted">{t("Angka taipan", "Typed figure")} ({mytText(m.entered_at, L)}) {t("tidak digunakan kerana bacaan langsung ada.", "is not used while a live reading exists.")}</p>}
    </div>
  );
}

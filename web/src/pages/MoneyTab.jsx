import { useMemo } from "react";
import { TABLES } from "../lib/SupabaseClient";
import { useLang } from "../lib/i18n";
import { useTable } from "../lib/hooks";
import { CATEGORY_WORDS } from "../lib/receipts";
import { cashFlowPeriods, moneyMovements, monthNet, mytDate } from "../lib/money";
import { PERSONAL, businessList, ofBusiness } from "../lib/businesses";
import { useView } from "../components/ViewToggle";
import GlassWorkspace from "@/components/ui/adjustable-glass-dashboard";

/* Ringkasan wang (Wan, 7 Nov 2026: the pasted glass dashboard, placed in Business as "Ringkasan wang (Disyorkan)"). The page
   reads three tables Semasa already keeps and hands the arithmetic to lib/money.js: money in = invoices marked paid, money out
   = purchase receipts plus subscription payments no receipt covers. Nothing here writes to the database; the glass setting
   Wan adjusts is kept in this browser only. A picker above it (supabase/066) shows every business together, one business, or
   personal (receipts and bills that belong to no business). */
const GLASS_KEY = "semasa.money.glass";
const MONTHS = { bm: ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ogo", "Sep", "Okt", "Nov", "Dis"], en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] };
const KIND = { income: "income", makan: "food", perjalanan: "travel", pengangkutan: "travel", bekalan: "shopping", langganan: "bills", utiliti: "bills" };

// Semasa's own colours, read by the dashboard's --gw-* variables, so it follows every theme the page has
const PALETTE = {
  "--gw-ink": "rgb(var(--c-ink))", "--gw-muted": "rgb(var(--c-muted))", "--gw-accent": "rgb(var(--c-accent))",
  "--gw-line": "rgb(var(--c-line))", "--gw-background": "rgb(var(--c-bg))", "--gw-surface": "rgb(var(--c-surface))",
  "--gw-panel": "rgb(var(--c-surface))", "--gw-highlight": "rgb(var(--c-surface))", "--gw-shade": "rgb(var(--c-bg) / 0.35)",
  "--gw-brand": "rgb(var(--c-ink))", "--gw-brand-ink": "rgb(var(--c-bg))", "--gw-button": "rgb(var(--c-ink))", "--gw-button-ink": "rgb(var(--c-bg))",
  "--gw-avatar": "rgb(var(--c-surface-2))", "--gw-dock": "rgb(var(--c-surface) / 0.7)", "--gw-dock-active": "rgb(var(--c-ink))", "--gw-dock-ink": "rgb(var(--c-bg))",
  "--gw-rail-active": "rgb(var(--c-surface-2))", "--gw-segment": "rgb(var(--c-surface-2) / 0.8)", "--gw-segment-active": "rgb(var(--c-surface))",
  "--gw-transaction-surface": "rgb(var(--c-surface-2))", "--gw-income-surface": "rgb(var(--c-accent) / 0.15)", "--gw-positive-surface": "rgb(var(--c-accent) / 0.15)",
  "--gw-account-surface": "rgb(var(--c-surface-2))", "--gw-account-action": "rgb(var(--c-surface-2))", "--gw-goal-surface": "rgb(var(--c-surface-2))",
  "--gw-search": "rgb(var(--c-surface) / 0.6)", "--gw-popover": "rgb(var(--c-surface) / 0.96)", "--gw-notification": "rgb(var(--c-surface) / 0.96)",
  "--gw-fallback": "rgb(var(--c-surface))", "--gw-mobile-dock": "rgb(var(--c-surface) / 0.6)", "--gw-toast": "rgb(var(--c-ink))", "--gw-toast-ink": "rgb(var(--c-bg))",
  "--gw-hover": "rgb(var(--c-surface-2) / 0.7)", "--gw-dock-hover": "rgb(var(--c-surface-2) / 0.7)", "--gw-control-hover": "rgb(var(--c-surface-2))",
  "--gw-pending": "rgb(var(--c-warn))", "--gw-selection": "rgb(var(--c-accent) / 0.3)",
  fontFamily: "inherit",
};

function savedGlass() {
  try { return JSON.parse(window.localStorage.getItem(GLASS_KEY) || "null") || undefined; } catch { return undefined; }
}

export default function MoneyTab({ user }) {
  const { t, lang } = useLang();
  const L = lang === "en" ? "en" : "bm";
  const docsT = useTable(TABLES.billingDocs, { enabled: true, limit: 3000, realtime: false });
  const rcptT = useTable(TABLES.receipts, { enabled: true, order: "doc_date", limit: 3000, realtime: false });
  const subsT = useTable(TABLES.subscriptions, { enabled: true, limit: 500, realtime: false });
  const bizT = useTable(TABLES.businesses, { enabled: true, order: "sort", ascending: true, limit: 50, realtime: false });
  const businesses = useMemo(() => businessList(bizT.rows), [bizT.rows]);
  const hasBusinesses = !bizT.error && bizT.rows.length > 0;
  // whose books (supabase/066): every business together, one business, or personal (receipts and bills with no business)
  const [pickRaw, setPick] = useView("money.business", "all");
  const pick = !hasBusinesses ? "all" : pickRaw === "all" || pickRaw === PERSONAL || businesses.some((b) => b.id === pickRaw) ? pickRaw : "all";
  const today = mytDate(new Date().toISOString());
  const moves = useMemo(() => moneyMovements({
    docs: pick === PERSONAL ? [] : ofBusiness(docsT.rows, pick),
    receipts: pick === "all" ? rcptT.rows : rcptT.rows.filter((r) => (r.business_id || PERSONAL) === pick),
    subs: pick === "all" ? subsT.rows : subsT.rows.filter((r) => (r.business_id || PERSONAL) === pick),
  }, today), [docsT.rows, rcptT.rows, subsT.rows, today, pick]);
  const pickName = pick === "all" ? t("Semua perniagaan", "All businesses") : pick === PERSONAL ? t("Peribadi", "Personal") : businesses.find((b) => b.id === pick)?.name || pick;
  const day = (d) => `${d.slice(8, 10)} ${MONTHS[L][Number(d.slice(5, 7)) - 1]}`;
  const periods = useMemo(() => cashFlowPeriods(moves, today, {
    week: t("Minggu", "Week"), month: t("30 hari", "30 days"), year: t("Tahun", "Year"), months: MONTHS[L], day,
  }), [moves, today, L]); // eslint-disable-line react-hooks/exhaustive-deps
  periods.forEach((p) => { p.description = t("Wang masuk = invois dibayar · wang keluar = resit belian dan langganan tanpa resit · ringgit sahaja, waktu Malaysia.",
    "Money in = invoices paid · money out = purchase receipts and subscriptions with no receipt · ringgit only, Malaysia time."); });
  const net = useMemo(() => monthNet(moves, today), [moves, today]);
  const catWord = (c) => (c === "income" ? t("Pendapatan", "Income") : (CATEGORY_WORDS[c] || [c, c])[L === "en" ? 1 : 0]);
  const transactions = moves.map((m) => ({ id: m.id, name: m.name, category: catWord(m.category), date: day(m.date), amount: m.amount, status: m.status, kind: KIND[m.category] || "other" }));
  const missing = [docsT, rcptT, subsT].map((x) => x.error).filter(Boolean);
  const name = (user?.user_metadata?.full_name || user?.email || "Wan").split(/[\s@]/)[0];

  return (
    <main className="mx-auto max-w-page px-4 pb-20 pt-6 sm:px-6" data-money>
      {missing.length > 0 && <p className="mb-4 rounded-tile bg-danger/10 p-3 text-sm text-danger">{missing.join(" · ")}</p>}
      {hasBusinesses && (
        <div role="tablist" aria-label={t("Buku siapa", "Whose books")} className="mb-4 flex flex-wrap gap-1.5" data-business-picker>
          {[["all", t("Semua", "All")], ...businesses.map((b) => [b.id, b.name]), [PERSONAL, t("Peribadi", "Personal")]].map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={id === pick} onClick={() => setPick(id)} data-business={id}
              className={`rounded-pill px-3 py-1 text-xs font-medium ${id === pick ? "bg-ink text-bg" : "bg-surface-2 text-muted hover:text-ink"}`}>{label}</button>
          ))}
        </div>
      )}
      <GlassWorkspace
        className="rounded-card"
        style={{ ...PALETTE, minHeight: "calc(100svh - 160px)" }}
        brand={t("Ringkasan wang", "Money overview")}
        userName={name}
        backgroundImage={`${import.meta.env.BASE_URL}cards/grounds/g_dokumen01.jpg`}
        balance={net.net}
        balanceChange={net.change != null ? { percent: net.change, label: t("berbanding bulan lepas", "compared with last month") } : undefined}
        periodLabel={`${MONTHS[L][Number(today.slice(5, 7)) - 1]} ${today.slice(0, 4)}`}
        cashFlowPeriods={periods}
        initialPeriodId="month"
        footerNote={t("Angka sebenar daripada Bil, Pembelian dan Langganan. Perkara menunggu tidak dikira dalam jumlah.",
          "Real figures from Billing, Purchases and Subscriptions. Pending items are not in the totals.")}
        transactions={transactions}
        goals={[]}
        currency="MYR"
        locale="ms-MY"
        useHostTheme
        showNotifications={false}
        glass={savedGlass()}
        onGlassChange={(g) => { try { window.localStorage.setItem(GLASS_KEY, JSON.stringify(g)); } catch { /* private window */ } }}
        labels={L === "en" ? { personal: pickName, balance: "Net this month", workspace: "Your money, from Semasa's own tables", welcome: "Hello, {name}." } : {
          personal: pickName, adjust: "Laras kaca", overview: "Ringkasan", activity: "Aktiviti", savings: "Simpanan", reports: "Laporan",
          welcome: "Hai, {name}.", workspace: "Wang anda, daripada jadual Semasa sendiri", savingsTitle: "Simpanan & matlamat", exportCsv: "Eksport CSV",
          balance: "Bersih bulan ini", viewAccount: "Lihat aktiviti", cashFlow: "Aliran tunai", moneyIn: "Wang masuk", moneyOut: "Wang keluar",
          recent: "Aktiviti terkini", viewAll: "Lihat semua", savingsGoals: "Matlamat simpanan", active: "aktif", transactions: "Transaksi",
          search: "Cari transaksi", clearSearch: "Kosongkan carian", noMatch: "Tiada transaksi sepadan", noTx: "Belum ada transaksi",
          tryAnother: "Cuba nama atau kategori lain.", txAppear: "Invois dibayar, resit belian dan langganan akan muncul di sini.",
          net: "Aliran tunai bersih", incomeExpenses: "Masuk & keluar", whereGoes: "Ke mana wang pergi", allActivity: "Semua aktiviti",
          noPeriod: "Tiada data tempoh", noCashTitle: "Belum ada data aliran tunai", noCashText: "Aliran tunai muncul bila ada invois dibayar atau resit.",
          glass: "Rupa kaca", glassText: "Laras bahan kaca di seluruh ruang ini (disimpan dalam pelayar ini).", preview: "Pratonton bahan",
          clear: "Jernih", frosted: "Kabur", solid: "Padu", blur: "Kabur", opacity: "Kelegapan", saturation: "Ketepuan", edge: "Cahaya tepi",
          tint: "Warna kaca", resetGlass: "Pulihkan rupa", completed: "Selesai", pending: "Menunggu", exported: "Transaksi dieksport.", of: "daripada",
          chartPeriod: "Tempoh carta", reportPeriod: "Tempoh laporan", quickNav: "Navigasi pantas", views: "Paparan", closeGlass: "Tutup tetapan kaca",
          csvHeader: "Nama,Kategori,Tarikh,Amaun,Status", csvFile: "transaksi.csv",
        }}
      />
    </main>
  );
}

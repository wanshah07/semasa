import GlassWorkspace, {
  type WorkspaceTransaction,
  type WorkspaceGoal,
  type WorkspaceCashFlowPeriod,
} from "@/components/ui/adjustable-glass-dashboard";

/* The pasted demo, sample figures only. The background picture is Semasa's own photograph (web/public/cards/grounds) instead
   of the third-party CDN address the paste carried. */
const transactions: WorkspaceTransaction[] = [
  { id: "1", name: "Studio retainer", category: "Income", date: "Today", amount: 4800, status: "Completed" },
  { id: "2", name: "Sunday Coffee", category: "Dining", date: "Today", amount: -18.5, status: "Completed" },
  { id: "3", name: "Aesop", category: "Shopping", date: "Yesterday", amount: -86, status: "Completed" },
  { id: "4", name: "Weekend in Sedona", category: "Travel", date: "Nov 03", amount: -320, status: "Pending" },
  { id: "5", name: "November rent", category: "Home", date: "Nov 01", amount: -1850, status: "Completed" },
];
const goals: WorkspaceGoal[] = [
  { id: "reserve", name: "Emergency fund", saved: 8400, target: 12000 },
  { id: "travel", name: "Travel fund", saved: 2350, target: 5000 },
];
const cashFlowPeriods: WorkspaceCashFlowPeriod[] = [
  {
    id: "week",
    label: "Week",
    description: "Sample daily totals for the selected week.",
    points: [
      { label: "Mon", income: 680, expenses: 112 },
      { label: "Tue", income: 940, expenses: 188 },
      { label: "Wed", income: 720, expenses: 84 },
      { label: "Thu", income: 1120, expenses: 245 },
      { label: "Fri", income: 760, expenses: 98 },
      { label: "Sat", income: 340, expenses: 174 },
      { label: "Sun", income: 240, expenses: 65 },
    ],
  },
];

export default function GlassWorkspaceDemo() {
  return (
    <GlassWorkspace
      brand="Automate Flows"
      userName="Troy"
      balance={28430.6}
      balanceChange={{ percent: 8.2, label: "compared with last month" }}
      account={{ name: "Everyday account", lastFour: "4829" }}
      periodLabel="November 2026"
      cashFlowPeriods={cashFlowPeriods}
      footerNote="All figures are sample data"
      transactions={transactions}
      goals={goals}
      backgroundImage={`${import.meta.env.BASE_URL}cards/grounds/g_dokumen01.jpg`}
    />
  );
}

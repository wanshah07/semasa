import { BarChart3, Brain, Clapperboard, Contact, Cpu, CreditCard, Droplets, GitBranch, ScanLine, FileText, HelpCircle, LayoutDashboard, LayoutTemplate, Lightbulb, ListChecks, MessageSquare, PenTool, Radio, Receipt, Settings, Sparkles } from "lucide-react";

/* Every tab, once: the header's tab row and the sidebar both read this list, so the two can never disagree.
   `group` places a tab in the sidebar: "" (top), "create", "business", "reference" or "bottom". */
export function tabsOf(t) {
  return [
    { id: "papan", label: t("Papan", "Dashboard"), icon: LayoutDashboard, group: "" },
    { id: "isu", label: t("Isu semasa", "Current issues"), icon: Radio, group: "" },
    { id: "idea", label: t("Idea", "Ideas"), icon: Lightbulb, group: "" },
    { id: "post", label: t("Post", "Posts"), icon: FileText, group: "" },
    { id: "prestasi", label: t("Prestasi", "Performance"), icon: BarChart3, group: "" },
    { id: "media", label: t("Makmal media", "Media lab"), icon: Sparkles, group: "create" },
    { id: "design", label: t("Reka bentuk", "Design"), icon: LayoutTemplate, group: "create" },
    { id: "wangian", label: t("Wangian", "Fragrance"), icon: Droplets, group: "create" },
    { id: "kanvas", label: "Kanvas", icon: PenTool, group: "create" },
    { id: "video", label: "Video", icon: Clapperboard, group: "create" },
    { id: "chat", label: t("Sembang AI", "AI chat"), icon: MessageSquare, group: "create" },
    { id: "otak", label: t("Otak AI", "AI brain"), icon: Brain, group: "create" },
    { id: "bil", label: t("Bil & Resit", "Billing"), icon: Receipt, group: "business" },
    { id: "langganan", label: t("Langganan", "Subscriptions"), icon: CreditCard, group: "business" },
    { id: "crm", label: "CRM", icon: Contact, group: "business" },
    { id: "resit", label: t("Resit", "Receipts"), icon: ScanLine, group: "business" },
    { id: "faq", label: "FAQ", icon: HelpCircle, group: "reference" },
    { id: "log", label: "Log", icon: ListChecks, group: "reference" },
    { id: "repo", label: t("Repo", "Repos"), icon: GitBranch, group: "reference" },
    { id: "api", label: "API", icon: Cpu, group: "reference" },
    { id: "tetapan", label: t("Tetapan", "Settings"), icon: Settings, group: "bottom" },
  ];
}

import { BarChart3, Brain, Building2, Clapperboard, Contact, Cpu, CreditCard, Droplets, FileText, GitBranch, HelpCircle, ImagePlus, LayoutDashboard,
  LayoutTemplate, Lightbulb, Library, ListChecks, MessageSquare, Newspaper, Radio, Receipt, ScanLine, Server, Settings, UserRound, Wrench } from "lucide-react";

/* Every page, once: the header's tab row on a phone, the sidebar and the sub-tab bar all read this list, so they can never
   disagree. A page's `id` is its address (#post, #office…) and does not change when it moves between segments.
   `segment` is the sidebar segment the page belongs to (Wan, 11 Oct 2026: "update the segment"). Settings has none: it stands
   alone at the bottom of the sidebar. */
export function tabsOf(t) {
  return [
    { id: "papan", label: t("Papan", "Dashboard"), icon: LayoutDashboard, segment: "dashboard" },
    { id: "chat", label: t("Sembang AI", "AI chat"), icon: MessageSquare, segment: "dashboard" },
    { id: "otak", label: t("Otak AI", "AI brain"), icon: Brain, segment: "dashboard" },

    { id: "isu", label: t("Isu semasa", "Current issues"), icon: Radio, segment: "content" },
    { id: "idea", label: t("Bank idea", "Ideas bank"), icon: Lightbulb, segment: "content" },
    { id: "post", label: t("Bank post", "Post bank"), icon: FileText, segment: "content" },

    { id: "prestasi", label: t("Prestasi", "Performance"), icon: BarChart3, segment: "performance" },

    { id: "media", label: t("Makmal media", "Media lab"), icon: ImagePlus, segment: "create" },
    { id: "design", label: t("Reka bentuk", "Design"), icon: LayoutTemplate, segment: "create" },
    { id: "video", label: "Video", icon: Clapperboard, segment: "create" },

    { id: "wangian", label: t("Wangian", "Fragrance"), icon: Droplets, segment: "valorith" },

    { id: "bil", label: t("Bil & Resit", "Billing"), icon: Receipt, segment: "business" },
    { id: "crm", label: "CRM", icon: Contact, segment: "business" },

    { id: "office", label: t("Repo pejabat", "Office repos"), icon: Building2, segment: "technology" },
    { id: "repo", label: t("Pustaka repo", "Repo library"), icon: GitBranch, segment: "technology" },
    { id: "api", label: "API", icon: Cpu, segment: "technology" },

    { id: "resit", label: t("Pembelian", "Purchases"), icon: ScanLine, segment: "personal" },
    { id: "langganan", label: t("Langganan", "Subscriptions"), icon: CreditCard, segment: "personal" },

    { id: "faq", label: "FAQ", icon: HelpCircle, segment: "reference" },
    { id: "log", label: "Log", icon: ListChecks, segment: "reference" },

    { id: "tetapan", label: t("Tetapan", "Settings"), icon: Settings, segment: "" },
  ];
}

/** The sidebar's segments, in order. A segment opens its first page; the pages it holds show as a sub-tab bar above the page
    (components/SegmentBar.jsx). A segment with one page has no bar. */
export function segmentsOf(t) {
  const pages = tabsOf(t);
  const seg = (id, label, icon) => ({ id, label, icon, pages: pages.filter((p) => p.segment === id) });
  return [
    seg("dashboard", t("Papan", "Dashboard"), LayoutDashboard),
    seg("content", t("Kandungan", "Content"), Newspaper),
    seg("performance", t("Prestasi", "Performance"), BarChart3),
    seg("create", t("Cipta", "Create"), Wrench),
    seg("valorith", "Valorith", Droplets),
    seg("business", t("Perniagaan", "Business"), Receipt),
    seg("technology", t("Teknologi", "Technology"), Server),
    seg("personal", t("Peribadi", "Personal"), UserRound),
    seg("reference", t("Rujukan", "Reference"), Library),
  ];
}

/** The segment a page sits in (null for Settings, which stands alone at the bottom). */
export function segmentOf(t, tabId) {
  return segmentsOf(t).find((s) => s.pages.some((p) => p.id === tabId)) || null;
}

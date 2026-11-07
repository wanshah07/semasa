import { Anchor, BarChart3, Brain, Building2, Clapperboard, Contact, Cpu, CreditCard, Droplets, FileText, Film, GitBranch, HelpCircle, ImagePlus, Images, LayoutDashboard,
  Layers, LayoutGrid, LayoutTemplate, Lightbulb, Library, ListChecks, MessageSquare, Newspaper, Radio, PenLine, Receipt, ScanLine, Server, Settings, Sparkles, UserRound, Wallet } from "lucide-react";

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
    { id: "hooks", label: t("Bank hook", "Hooks bank"), icon: Anchor, segment: "content" },
    { id: "gaya", label: t("Gaya penulisan", "Writing styles"), icon: PenLine, segment: "content" },

    { id: "prestasi", label: t("Prestasi", "Performance"), icon: BarChart3, segment: "performance" },

    { id: "media", label: t("Jana imej", "Generate image"), icon: ImagePlus, segment: "image" },
    { id: "media-lib", label: t("Pustaka imej", "Image library"), icon: Images, segment: "image" },

    { id: "video", label: t("Jana video", "Generate video"), icon: Clapperboard, segment: "video" },
    { id: "video-lib", label: t("Pustaka video", "Video library"), icon: Film, segment: "video" },
    { id: "motion-skills", label: t("Kemahiran motion", "Motion skills"), icon: Sparkles, segment: "video" },

    { id: "design", label: t("Jana poster", "Generate poster"), icon: LayoutTemplate, segment: "poster" },
    { id: "design-lib", label: t("Pustaka poster", "Poster library"), icon: LayoutGrid, segment: "poster" },

    { id: "wangian", label: t("Wangian", "Fragrance"), icon: Droplets, segment: "valorith" },
    { id: "bil-valorith", label: t("Bil Valorith", "Valorith billing"), icon: Receipt, segment: "valorith" },

    { id: "wang", label: t("Ringkasan wang", "Money overview"), icon: Wallet, segment: "business" },
    { id: "bil", label: t("Bil & Resit", "Billing"), icon: Receipt, segment: "business" },
    { id: "crm", label: "CRM", icon: Contact, segment: "business" },
    { id: "syarikat", label: t("Syarikat", "Businesses"), icon: Building2, segment: "business" },

    { id: "tech", label: t("Ringkasan", "Overview"), icon: Server, segment: "technology" },
    { id: "office", label: t("Repo pejabat", "Office repos"), icon: Building2, segment: "technology" },
    { id: "repo", label: t("Pustaka repo", "Repo library"), icon: GitBranch, segment: "technology" },
    { id: "api", label: "API", icon: Cpu, segment: "technology" },
    { id: "stack", label: t("Senarai teknologi", "Technology list"), icon: Layers, segment: "technology" },

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
    seg("image", t("Imej", "Image"), ImagePlus),
    seg("video", "Video", Clapperboard),
    seg("poster", "Poster", LayoutTemplate),
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

/** The phone's bottom bar (components/MobileTabBar.jsx): the five places Wan opens most, one thumb tap away; everything
    else is in the menu. `match` lists the pages that light a button up as well as its own, so Video stays lit on the
    video library. Labels are short: five have to fit in 375 px. */
export function mobileTabsOf(t) {
  const byId = Object.fromEntries(tabsOf(t).map((p) => [p.id, p]));
  const item = (id, label, match = []) => ({ id, label, icon: byId[id].icon, match: [id, ...match] });
  return [
    item("papan", t("Papan", "Home")),
    item("idea", "Idea"),
    item("post", "Post"),
    item("video", "Video", ["video-lib", "motion-skills"]),
    item("chat", t("Sembang", "Chat")),
  ];
}

import { Clapperboard, Droplets, FileText, HelpCircle, LayoutTemplate, Lightbulb, ListChecks, PenTool, Radio, Settings, Sparkles } from "lucide-react";

/* Every tab, once: the header's tab row and the sidebar both read this list, so the two can never disagree.
   `group` places a tab in the sidebar: "" (top), "create", "reference" or "bottom". */
export function tabsOf(t) {
  return [
    { id: "isu", label: t("Isu semasa", "Current issues"), icon: Radio, group: "" },
    { id: "idea", label: t("Idea", "Ideas"), icon: Lightbulb, group: "" },
    { id: "post", label: t("Post", "Posts"), icon: FileText, group: "" },
    { id: "media", label: t("Makmal media", "Media lab"), icon: Sparkles, group: "create" },
    { id: "design", label: t("Reka bentuk", "Design"), icon: LayoutTemplate, group: "create" },
    { id: "wangian", label: t("Wangian", "Fragrance"), icon: Droplets, group: "create" },
    { id: "kanvas", label: "Kanvas", icon: PenTool, group: "create" },
    { id: "video", label: "Video", icon: Clapperboard, group: "create" },
    { id: "faq", label: "FAQ", icon: HelpCircle, group: "reference" },
    { id: "log", label: "Log", icon: ListChecks, group: "reference" },
    { id: "tetapan", label: t("Tetapan", "Settings"), icon: Settings, group: "bottom" },
  ];
}

"use client";

/* The AI chat composer, pasted from 21st.dev "ai-04" (Wan, 29 Sep 2026: "add one segment for AI chat, later then I
   will connect with API, just blank structure"). Semasa is Vite + React 18 + Tailwind 3 + Radix, not Next.js + Tailwind
   4 + Base UI, so these are the changes, and nothing else:
   - next/image -> a plain <img> (there is no Next.js here);
   - DropdownMenuTrigger `render={<Button/>}` (Base UI's API) -> Radix's `asChild` with the Button inside;
   - Tailwind 4 spellings -> Tailwind 3: max-w-30 -> max-w-[7.5rem], max-h-50 -> max-h-[12.5rem],
     max-w-250 -> max-w-[62.5rem], bg-transparent! -> !bg-transparent, font-heading -> font-display. Under Tailwind 3
     the original spellings compile to nothing, silently;
   - the words, the quick actions and the placeholder are props (defaults are the original English), so the page can
     speak BM and offer Semasa's own starters; a quick action fills the box instead of doing nothing;
   - onSubmit also hands over the attached files and the three switches, and the attachments clear after sending;
   - "Import from URL" and "Use Template" are shown disabled until they do something: a menu item that does nothing
     when clicked reads as broken. "Paste from Clipboard" pastes. */

import {
  IconAdjustmentsHorizontal,
  IconArrowUp,
  IconBrandFigma,
  IconCamera,
  IconCirclePlus,
  IconClipboard,
  IconFileUpload,
  IconHistory,
  IconLayoutDashboard,
  IconLink,
  IconPaperclip,
  IconPlayerPlay,
  IconPlus,
  IconSparkles,
  IconTemplate,
  IconX,
} from "@tabler/icons-react";
import { type ComponentType, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/ai-04-utils/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/ai-04-utils/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

interface AttachedFile {
  id: string;
  name: string;
  file: File;
  preview?: string;
}

export interface Ai04Action {
  id: string;
  icon: ComponentType<{ size?: number | string; className?: string }>;
  label: string;
  /** what the action puts in the box; the label itself when absent */
  prompt?: string;
}

export interface Ai04Settings {
  autoComplete: boolean;
  streaming: boolean;
  showHistory: boolean;
}

export interface Ai04Labels {
  attach: string;
  url: string;
  paste: string;
  template: string;
  soon: string;
  autoComplete: string;
  streaming: string;
  showHistory: string;
  drop: string;
  send: string;
  add: string;
  adjust: string;
  remove: string;
}

const ACTIONS: Ai04Action[] = [
  { id: "clone-screenshot", icon: IconCamera, label: "Clone a Screenshot" },
  { id: "import-figma", icon: IconBrandFigma, label: "Import from Figma" },
  { id: "upload-project", icon: IconFileUpload, label: "Upload a Project" },
  { id: "landing-page", icon: IconLayoutDashboard, label: "Landing Page" },
];

const LABELS: Ai04Labels = {
  attach: "Attach Files",
  url: "Import from URL",
  paste: "Paste from Clipboard",
  template: "Use Template",
  soon: "soon",
  autoComplete: "Auto-complete",
  streaming: "Streaming",
  showHistory: "Show History",
  drop: "Drop files here to add as attachments",
  send: "Send message",
  add: "Add attachments",
  adjust: "Adjust settings",
  remove: "Remove",
};

export default function Ai04({
  onSubmit,
  title = "Prompt. Refine. Ship.",
  subtitle = "Build real, working software just by describing it",
  placeholder = "Ask anything",
  actions = ACTIONS,
  labels: labelsIn,
  busy = false,
}: {
  onSubmit?: (prompt: string, extra: { files: File[]; settings: Ai04Settings }) => void;
  title?: string | null;
  subtitle?: string | null;
  placeholder?: string;
  actions?: Ai04Action[];
  labels?: Partial<Ai04Labels>;
  /** true while an answer is on its way: the send button waits */
  busy?: boolean;
}) {
  const L = { ...LABELS, ...labelsIn };
  const [prompt, setPrompt] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  const [settings, setSettings] = useState<Ai04Settings>({
    autoComplete: true,
    streaming: false,
    showHistory: false,
  });

  const generateFileId = () => Math.random().toString(36).substring(7);
  const processFiles = (files: File[]) => {
    for (const file of files) {
      const fileId = generateFileId();
      const attachedFile: AttachedFile = {
        id: fileId,
        name: file.name,
        file,
      };

      if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = () => {
          setAttachedFiles((prev) =>
            prev.map((f) =>
              f.id === fileId ? { ...f, preview: reader.result as string } : f,
            ),
          );
        };
        reader.readAsDataURL(file);
      }

      setAttachedFiles((prev) => [...prev, attachedFile]);
    }
  };
  const submitPrompt = () => {
    if (prompt.trim() && onSubmit && !busy) {
      onSubmit(prompt.trim(), { files: attachedFiles.map((f) => f.file), settings });
      setPrompt("");
      setAttachedFiles([]);
    }
  };
  const updateSetting = (key: keyof Ai04Settings, value: boolean) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };
  const fill = (text: string) => {
    setPrompt(text);
    requestAnimationFrame(() => textRef.current?.focus());
  };
  const pasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) fill(prompt ? `${prompt}\n${text}` : text);
    } catch {
      textRef.current?.focus(); // the browser said no: Ctrl+V in the box still works
    }
  };
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitPrompt();
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) {
      processFiles(files);
    }
  };
  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setPrompt(e.target.value);
  };
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitPrompt();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    processFiles(files);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveFile = (fileId: string) => {
    setAttachedFiles((prev) => prev.filter((file) => file.id !== fileId));
  };

  return (
    <div className="mx-auto flex w-full flex-col gap-4">
      {title && (
        <h1 className="text-balance text-pretty text-center font-display font-semibold text-[29px] text-foreground tracking-tighter sm:text-[32px] md:text-[46px]">
          {title}
        </h1>
      )}
      {subtitle && (
        <h2 className="-my-5 text-balance pb-4 text-center text-muted-foreground text-xl">
          {subtitle}
        </h2>
      )}

      <div className="relative z-10 mx-auto flex w-full max-w-2xl flex-col content-center">
        <form
          className="overflow-visible rounded-xl border bg-surface p-2 transition-colors duration-200 focus-within:border-ring"
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onSubmit={handleSubmit}
        >
          {attachedFiles.length > 0 && (
            <div className="relative mb-2 flex w-fit flex-wrap items-center gap-2 overflow-hidden">
              {attachedFiles.map((file) => (
                <Badge
                  className="group relative h-6 max-w-[7.5rem] cursor-pointer overflow-hidden px-0 text-[13px] transition-colors hover:bg-surface-2"
                  key={file.id}
                  variant="outline"
                >
                  <span className="flex h-full items-center gap-1.5 overflow-hidden pl-1 font-normal">
                    <div className="relative flex h-4 min-w-4 items-center justify-center">
                      {file.preview ? (
                        <img
                          alt={file.name}
                          className="absolute inset-0 h-4 w-4 rounded border object-cover"
                          height={16}
                          src={file.preview}
                          width={16}
                        />
                      ) : (
                        <IconPaperclip className="opacity-60" size={12} />
                      )}
                    </div>
                    <span className="inline overflow-hidden truncate pr-1.5">
                      {file.name}
                    </span>
                  </span>
                  <button
                    aria-label={`${L.remove} ${file.name}`}
                    className="absolute right-1 z-10 rounded-sm bg-surface p-0.5 text-muted-foreground opacity-0 focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-background group-hover:opacity-100"
                    onClick={() => handleRemoveFile(file.id)}
                    type="button"
                  >
                    <IconX size={12} />
                  </button>
                </Badge>
              ))}
            </div>
          )}
          <Textarea
            ref={textRef}
            className="max-h-[12.5rem] min-h-12 resize-none rounded-none border-none !bg-transparent p-0 text-sm shadow-none focus-visible:border-transparent focus-visible:ring-0 focus-visible:ring-offset-0"
            onChange={handleTextareaChange}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            value={prompt}
          />

          <div className="flex items-center gap-1">
            <div className="flex items-end gap-0.5 sm:gap-1">
              <input
                className="sr-only"
                multiple
                onChange={handleFileSelect}
                ref={fileInputRef}
                tabIndex={-1}
                type="file"
              />

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    aria-label={L.add}
                    className="ml-[-2px] rounded-md"
                    size="icon-sm"
                    type="button"
                    variant="ghost"
                  >
                    <IconPlus size={16} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="start"
                  className="max-w-xs rounded-2xl p-1.5"
                >
                  <DropdownMenuGroup className="space-y-1">
                    <DropdownMenuItem
                      className="rounded-md text-xs"
                      onSelect={() => fileInputRef.current?.click()}
                    >
                      <div className="flex items-center gap-2">
                        <IconPaperclip
                          className="text-muted-foreground"
                          size={16}
                        />
                        <span>{L.attach}</span>
                      </div>
                    </DropdownMenuItem>
                    <DropdownMenuItem className="rounded-md text-xs" disabled>
                      <div className="flex items-center gap-2">
                        <IconLink className="text-muted-foreground" size={16} />
                        <span>{L.url}</span>
                        <span className="text-[10px] text-muted-foreground">· {L.soon}</span>
                      </div>
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="rounded-md text-xs"
                      onSelect={() => { void pasteClipboard(); }}
                    >
                      <div className="flex items-center gap-2">
                        <IconClipboard
                          className="text-muted-foreground"
                          size={16}
                        />
                        <span>{L.paste}</span>
                      </div>
                    </DropdownMenuItem>
                    <DropdownMenuItem className="rounded-md text-xs" disabled>
                      <div className="flex items-center gap-2">
                        <IconTemplate
                          className="text-muted-foreground"
                          size={16}
                        />
                        <span>{L.template}</span>
                        <span className="text-[10px] text-muted-foreground">· {L.soon}</span>
                      </div>
                    </DropdownMenuItem>
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    aria-label={L.adjust}
                    className="rounded-md"
                    size="icon-sm"
                    type="button"
                    variant="ghost"
                  >
                    <IconAdjustmentsHorizontal size={16} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="start"
                  className="w-52 rounded-2xl p-3"
                >
                  <DropdownMenuGroup className="space-y-3">
                    {([
                      ["autoComplete", IconSparkles, L.autoComplete],
                      ["streaming", IconPlayerPlay, L.streaming],
                      ["showHistory", IconHistory, L.showHistory],
                    ] as const).map(([key, Icon, label]) => (
                      <div className="flex items-center justify-between" key={key}>
                        <div className="flex items-center gap-2">
                          <Icon className="text-muted-foreground" size={16} />
                          <Label className="text-xs" htmlFor={`ai04-${key}`}>{label}</Label>
                        </div>
                        <Switch
                          id={`ai04-${key}`}
                          checked={settings[key]}
                          className="scale-75"
                          onCheckedChange={(value) => updateSetting(key, value)}
                        />
                      </div>
                    ))}
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <div className="ml-auto flex items-center gap-0.5 sm:gap-1">
              <Button
                aria-label={L.send}
                className="rounded-md"
                disabled={!prompt.trim() || busy}
                size="icon-sm"
                type="submit"
                variant="default"
              >
                <IconArrowUp size={16} />
              </Button>
            </div>
          </div>

          <div
            className={cn(
              "pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-[inherit] border border-border border-dashed bg-muted text-foreground text-sm transition-opacity duration-200",
              isDragOver ? "opacity-100" : "opacity-0",
            )}
          >
            <span className="flex w-full items-center justify-center gap-1 font-medium">
              <IconCirclePlus className="min-w-4" size={16} />
              {L.drop}
            </span>
          </div>
        </form>
      </div>

      {actions.length > 0 && (
        <div className="mx-auto flex min-h-0 max-w-[62.5rem] shrink-0 flex-wrap items-center justify-center gap-3">
          {actions.map((action) => (
            <Button
              className="gap-2 rounded-full"
              key={action.id}
              onClick={() => fill(action.prompt ?? action.label)}
              size="sm"
              type="button"
              variant="outline"
            >
              <action.icon size={16} />
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

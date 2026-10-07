"use client";
/* The documents table of Bil (Wan, 7 Oct 2026), built from the pasted 21st.dev "table-2" invoices block. What changed to
   fit Semasa, and why:
   - the rows come in as props (`rows`, from semasa_billing_docs) instead of the eighteen sample invoices;
   - the icon placeholders became lucide icons, the Base UI `render=` trigger became Radix `asChild`, `sonner` became the
     page's own toast (`onToast`): Semasa's shadcn files are the Radix line, and a pasted class a build does not have is
     silently nothing (ops/MY-DESIGNS.md records the Tailwind lesson);
   - the actions (view, download, send, reminder, mark paid, convert, void, delete) call back to the page, which owns the
     database writes and the rules (web/src/lib/billing.js);
   - the status badge reads the DERIVED status (overdue, expired) so a date that passed while Semasa was shut shows red;
   - column filtering is declared explicitly (the pasted comment is right: a column with no filterFn filters nothing).
   @tanstack/react-table 9 (the API the pasted block was written against) is what npm installs today. */
import * as React from "react";
import {
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  columnFilteringFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  flexRender,
  rowPaginationFeature,
  rowSelectionFeature,
  rowSortingFeature,
  sortFn_basic,
  sortFn_datetime,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import {
  ArrowDown, ArrowUp, Bell, Check, ChevronLeft, ChevronRight, ChevronsUpDown, Copy, Download, Ellipsis, Eye, FileCheck2,
  Link2, Mail, Pencil, Receipt, Search, Trash2, XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/table-2-utils/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/table-2-utils/checkbox";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/table-2-utils/dropdown-menu";
import { Input } from "@/components/ui/table-2-utils/input";
import { Separator } from "@/components/ui/table-2-utils/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table-2-utils/table";

const TABLE_FEATURES = tableFeatures({
  columnVisibilityFeature,
  rowSortingFeature,
  columnFilteringFeature,
  rowPaginationFeature,
  rowSelectionFeature,
  sortedRowModel: createSortedRowModel(),
  filteredRowModel: createFilteredRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  sortFns: { datetime: sortFn_datetime, basic: sortFn_basic },
});

export type DocRow = {
  id: string;
  kind: "quotation" | "invoice" | "receipt";
  number: string | null;
  status: string;            // stored
  effective: string;         // derived (billing.js effectiveStatus)
  client: string;
  initials: string;
  reference: string;
  total: number;
  currency: string;
  issue_date: string | null;
  due_date: string | null;
  sent_at?: string | null;
  viewed_at?: string | null;
  pdf_url?: string | null;
};

export type DocAction = "view" | "edit" | "download" | "send" | "reminder" | "paid" | "convert" | "void" | "delete" | "link" | "duplicate"
  | "accepted" | "declined";

export type TableWords = {
  title: string; subtitle: string; company: string; outstanding: string; filter: string; results: (n: number) => string; selected: string;
  clear: string; download: string; reminder: string; markPaid: string; none: string; docs: (n: number) => string; page: (a: number, b: number) => string;
  columns: { number: string; client: string; reference: string; issued: string; due: string; status: string; amount: string };
  kinds: Record<string, string>; statuses: Record<string, string>;
  actions: Record<DocAction, string>;
  footer: string;
};

const statusTone: Record<string, { variant: "default" | "secondary" | "destructive" | "outline"; dot: string }> = {
  paid: { variant: "default", dot: "bg-primary-foreground" },
  accepted: { variant: "default", dot: "bg-primary-foreground" },
  converted: { variant: "default", dot: "bg-primary-foreground" },
  sent: { variant: "secondary", dot: "bg-muted-foreground" },
  viewed: { variant: "secondary", dot: "bg-muted-foreground" },
  issued: { variant: "secondary", dot: "bg-muted-foreground" },
  draft: { variant: "outline", dot: "bg-muted-foreground" },
  overdue: { variant: "destructive", dot: "bg-destructive-foreground" },
  expired: { variant: "destructive", dot: "bg-destructive-foreground" },
  declined: { variant: "destructive", dot: "bg-destructive-foreground" },
  void: { variant: "outline", dot: "bg-muted-foreground" },
};

const fmt = (n: number, cur: string) => `${cur} ${new Intl.NumberFormat("en-MY", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0)}`;
const fmtDate = (iso: string | null | undefined) => (iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso || "—");

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") return <ArrowUp className="size-3.5" aria-hidden="true" />;
  if (sorted === "desc") return <ArrowDown className="size-3.5" aria-hidden="true" />;
  return <ChevronsUpDown className="size-3.5 text-muted-foreground/60" aria-hidden="true" />;
}

const headLabel = "text-xs font-semibold tracking-wider text-muted-foreground uppercase";
const sortButton = "-mx-1 inline-flex items-center gap-1 rounded-md px-1 text-xs font-semibold tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground";

/** Which row actions a document offers, by kind and derived status. The page enforces the same rules on the writes. */
export function actionsFor(row: DocRow): DocAction[] {
  const s = row.effective;
  const out: DocAction[] = ["view"];
  if (s === "draft") out.push("edit");
  out.push("download");
  if (s !== "draft" && s !== "void") out.push("link");
  if (s !== "draft" && s !== "void") out.push("send");
  if (row.kind === "invoice" && ["sent", "viewed", "overdue", "issued"].includes(s)) out.push("reminder", "paid");
  if (row.kind === "quotation" && ["issued", "sent", "viewed", "accepted", "expired"].includes(s)) out.push("convert");
  if (row.kind === "quotation" && ["issued", "sent", "viewed"].includes(s)) out.push("accepted", "declined");
  out.push("duplicate");
  if (row.kind === "invoice" && ["issued", "sent", "viewed", "overdue"].includes(s)) out.push("void");
  if (s === "draft") out.push("delete");
  return out;
}

const ACTION_ICON: Record<DocAction, React.ComponentType<{ className?: string }>> = {
  view: Eye, edit: Pencil, download: Download, send: Mail, reminder: Bell, paid: Check, convert: Receipt, void: XCircle, delete: Trash2,
  link: Link2, duplicate: Copy, accepted: FileCheck2, declined: XCircle,
};

export default function DocumentsTable({ rows, words, onAction, onBulk, pageSize = 8, emptyHint }: {
  rows: DocRow[];
  words: TableWords;
  onAction: (action: DocAction, row: DocRow) => void;
  onBulk: (action: "download" | "reminder" | "paid", rows: DocRow[]) => void;
  pageSize?: number;
  emptyHint?: string;
}) {
  const [sorting, setSorting] = React.useState<SortingState>([{ id: "issue_date", desc: true }]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [rowSelection, setRowSelection] = React.useState({});

  const columns = React.useMemo<ColumnDef<typeof TABLE_FEATURES, DocRow>[]>(() => [
    {
      id: "select",
      enableSorting: false,
      enableHiding: false,
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          indeterminate={table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected()}
          onCheckedChange={(checked) => table.toggleAllPageRowsSelected(checked === true)}
          aria-label="Select all documents on this page"
        />
      ),
      cell: ({ row }) => (
        <Checkbox checked={row.getIsSelected()} onCheckedChange={(checked) => row.toggleSelected(checked === true)}
          aria-label={`Select ${row.original.number || "draft"}`} />
      ),
    },
    {
      accessorKey: "number",
      header: ({ column }) => (
        <button type="button" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} className={sortButton}>
          {words.columns.number}<SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ row }) => (
        <button type="button" onClick={() => onAction("view", row.original)} className="text-left">
          <span className="block font-mono text-xs text-foreground">{row.original.number || <span className="text-muted-foreground">{words.statuses.draft}</span>}</span>
          <span className="block text-[10px] uppercase tracking-wider text-muted-foreground">{words.kinds[row.original.kind]}</span>
        </button>
      ),
    },
    {
      accessorKey: "client",
      filterFn: (row, _id, value: string) => {
        const q = String(value || "").toLowerCase();
        const r = row.original;
        return [r.client, r.number, r.reference].some((x) => String(x || "").toLowerCase().includes(q));
      },
      header: ({ column }) => (
        <button type="button" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} className={sortButton}>
          {words.columns.client}<SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ row }) => (
        <div className="flex min-w-0 items-center gap-2.5">
          <Avatar size="sm" className="shrink-0 border border-border">
            <AvatarFallback className="text-[10px]">{row.original.initials}</AvatarFallback>
          </Avatar>
          <span className="truncate text-sm font-medium text-foreground">{row.original.client}</span>
        </div>
      ),
    },
    {
      accessorKey: "reference",
      enableSorting: false,
      header: () => <span className={headLabel}>{words.columns.reference}</span>,
      cell: ({ row }) => <span className="block max-w-[140px] truncate text-sm text-muted-foreground">{row.original.reference || "—"}</span>,
    },
    {
      accessorKey: "issue_date",
      sortFn: "datetime",
      sortUndefined: "last",
      accessorFn: (r) => (r.issue_date ? new Date(r.issue_date) : undefined),
      header: ({ column }) => (
        <button type="button" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} className={sortButton}>
          {words.columns.issued}<SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ row }) => <span className="text-sm text-muted-foreground tabular-nums">{fmtDate(row.original.issue_date)}</span>,
    },
    {
      accessorKey: "due_date",
      sortFn: "datetime",
      sortUndefined: "last",
      accessorFn: (r) => (r.due_date ? new Date(r.due_date) : undefined),
      header: ({ column }) => (
        <button type="button" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} className={sortButton}>
          {words.columns.due}<SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ row }) => (
        <span className={cn("text-sm tabular-nums", row.original.effective === "overdue" ? "font-semibold text-destructive" : "text-muted-foreground")}>
          {row.original.kind === "receipt" ? "—" : fmtDate(row.original.due_date)}
        </span>
      ),
    },
    {
      accessorKey: "effective",
      enableSorting: false,
      header: () => <span className={headLabel}>{words.columns.status}</span>,
      cell: ({ row }) => {
        const cfg = statusTone[row.original.effective] || statusTone.draft;
        return (
          <Badge variant={cfg.variant} className="gap-1.5 text-[11px] font-medium">
            <span className={cn("inline-block size-1.5 shrink-0 rounded-full", cfg.dot)} aria-hidden="true" />
            {words.statuses[row.original.effective] || row.original.effective}
          </Badge>
        );
      },
    },
    {
      accessorKey: "total",
      sortFn: "basic",
      header: ({ column }) => (
        <div className="flex justify-end">
          <button type="button" onClick={() => column.toggleSorting(column.getIsSorted() === "asc")} className={sortButton}>
            {words.columns.amount}<SortIcon sorted={column.getIsSorted()} />
          </button>
        </div>
      ),
      cell: ({ row }) => (
        <span className="block text-right text-sm font-semibold text-foreground tabular-nums">{fmt(row.original.total, row.original.currency)}</span>
      ),
    },
    {
      id: "actions",
      enableSorting: false,
      enableHiding: false,
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => {
        const acts = actionsFor(row.original);
        return (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${row.original.number || "draft"}`}>
                  <Ellipsis className="size-4" aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                {acts.map((a, i) => {
                  const Icon = ACTION_ICON[a];
                  const danger = a === "void" || a === "delete" || a === "declined";
                  return (
                    <React.Fragment key={a}>
                      {(a === "duplicate" || (danger && acts[i - 1] && !["void", "delete", "declined"].includes(acts[i - 1]))) && <DropdownMenuSeparator />}
                      <DropdownMenuItem onSelect={() => onAction(a, row.original)} className={cn("gap-2", danger && "text-destructive focus:text-destructive")}>
                        <Icon className="size-3.5" aria-hidden="true" />{words.actions[a]}
                      </DropdownMenuItem>
                    </React.Fragment>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
    },
  ], [words, onAction]);

  const table = useTable({
    features: TABLE_FEATURES,
    data: rows,
    columns,
    getRowId: (row) => row.id,
    state: { sorting, columnFilters, rowSelection },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onRowSelectionChange: setRowSelection,
    initialState: { pagination: { pageIndex: 0, pageSize } },
  });

  const clientFilter = (table.getColumn("client")?.getFilterValue() as string) ?? "";
  const selectedRows = table.getFilteredSelectedRowModel().rows.map((r) => r.original);
  const selectedCount = selectedRows.length;
  const totalCount = table.getFilteredRowModel().rows.length;
  const pageCount = table.getPageCount();
  const outstanding = rows.filter((r) => r.kind === "invoice" && ["issued", "sent", "viewed", "overdue"].includes(r.effective))
    .reduce((s, r) => s + (r.total || 0), 0);
  const cur = rows[0]?.currency || "MYR";
  const canPay = selectedRows.filter((r) => r.kind === "invoice" && ["issued", "sent", "viewed", "overdue"].includes(r.effective));
  const canRemind = selectedRows.filter((r) => r.kind === "invoice" && ["sent", "viewed", "overdue"].includes(r.effective));

  return (
    <section className="w-full text-foreground" data-testid="documents-table">
      <div className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <p className="text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">{words.company}</p>
          <h2 className="font-heading text-xl font-semibold tracking-tight text-foreground">{words.title}</h2>
          <p className="text-sm text-muted-foreground">{words.subtitle}</p>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] tracking-widest text-muted-foreground uppercase">{words.outstanding}</span>
          <span className="text-lg font-semibold text-foreground tabular-nums">{fmt(outstanding, cur)}</span>
        </div>
      </div>

      <Separator className="my-5" />

      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input type="search" value={clientFilter} onChange={(event) => table.getColumn("client")?.setFilterValue(event.target.value)}
            placeholder={words.filter} className="w-56 pl-8 text-sm" aria-label={words.filter} />
        </div>
        <p className="text-xs text-muted-foreground"><span className="font-medium text-foreground">{totalCount}</span> {words.results(totalCount)}</p>
      </div>

      {selectedCount > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground tabular-nums">{selectedCount} {words.selected}</span>
            <Button variant="ghost" size="xs" className="text-muted-foreground hover:text-foreground" onClick={() => table.resetRowSelection()}>{words.clear}</Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => onBulk("download", selectedRows)}>
              <Download className="mr-1.5 size-3.5" aria-hidden="true" />{words.download}
            </Button>
            <Button variant="outline" size="sm" disabled={!canRemind.length} onClick={() => onBulk("reminder", canRemind)}>
              <Mail className="mr-1.5 size-3.5" aria-hidden="true" />{words.reminder}{canRemind.length ? ` (${canRemind.length})` : ""}
            </Button>
            <Button variant="outline" size="sm" disabled={!canPay.length} onClick={() => onBulk("paid", canPay)}>
              <Check className="mr-1.5 size-3.5" aria-hidden="true" />{words.markPaid}{canPay.length ? ` (${canPay.length})` : ""}
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="bg-muted/40 hover:bg-muted/40">
                {headerGroup.headers.map((header) => {
                  const id = header.column.id;
                  return (
                    <TableHead key={header.id} className={cn("h-9",
                      id === "select" && "w-10 pl-4",
                      id === "reference" && "hidden lg:table-cell",
                      (id === "issue_date" || id === "due_date") && "hidden md:table-cell",
                      id === "total" && "text-right",
                      id === "actions" && "w-10 pr-4")}>
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow key={row.id} data-state={row.getIsSelected() ? "selected" : undefined}
                  className="border-b border-border/60 transition-colors last:border-b-0 hover:bg-muted/30">
                  {row.getVisibleCells().map((cell) => {
                    const id = cell.column.id;
                    return (
                      <TableCell key={cell.id} className={cn("py-3",
                        id === "select" && "pl-4",
                        id === "reference" && "hidden lg:table-cell",
                        (id === "issue_date" || id === "due_date") && "hidden md:table-cell",
                        id === "actions" && "pr-4")}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))
            ) : (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={columns.length} className="h-24 text-center text-sm text-muted-foreground">{emptyHint || words.none}</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        <div className="flex items-center justify-between gap-4 border-t border-border bg-muted/20 px-4 py-2.5">
          <p className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">{words.docs(totalCount)}</p>
          <div className="flex items-center gap-1.5">
            <Button variant="outline" size="icon" className="size-7" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} aria-label="Previous page">
              <ChevronLeft className="size-3.5" aria-hidden="true" />
            </Button>
            <span className="px-1 text-xs text-muted-foreground tabular-nums">{words.page(table.state.pagination.pageIndex + 1, Math.max(pageCount, 1))}</span>
            <Button variant="outline" size="icon" className="size-7" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} aria-label="Next page">
              <ChevronRight className="size-3.5" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-muted-foreground">{words.footer}</p>
    </section>
  );
}

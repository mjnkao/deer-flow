"use client";

import {
  Activity,
  ChevronDown,
  ChevronRight,
  FileText,
  ListPlus,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  PlusIcon,
  Search,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useAgents } from "@/core/agents";
import { useModuleFlags } from "@/core/modules";
import {
  useCreateWorkUnit,
  useUpdateWorkUnit,
  useWorkUnits,
  type WorkUnit,
} from "@/core/work-units";

const LEAD_AGENT_NAME = "lead_agent";

const WorkUnitChatPanel = dynamic(
  () => import("./work-unit-chat-panel").then((mod) => mod.WorkUnitChatPanel),
  {
    loading: () => (
      <div className="text-muted-foreground flex flex-1 items-center justify-center p-6 text-center text-sm">
        Loading chat...
      </div>
    ),
  },
);

const WorkUnitTracePanel = dynamic(
  () => import("./work-unit-trace-panel").then((mod) => mod.WorkUnitTracePanel),
  {
    loading: () => (
      <div className="text-muted-foreground flex flex-1 items-center justify-center p-6 text-center text-sm">
        Loading trace...
      </div>
    ),
  },
);

const STATUS_COLUMNS = [
  {
    value: "backlog",
    label: "Backlog",
    description: "Captured or proposed work that is not dispatchable yet.",
  },
  {
    value: "ready",
    label: "Ready",
    description: "Dispatchable work with minimum required context.",
  },
  {
    value: "in_progress",
    label: "Running",
    description: "Active execution by human, agent, or runtime.",
  },
  {
    value: "blocked",
    label: "Waiting",
    description: "Paused on dependency, external input, gate, or resume condition.",
  },
  {
    value: "review",
    label: "Review",
    description: "Output or evidence exists and needs acceptance.",
  },
  {
    value: "done",
    label: "Done",
    description: "Completed, accepted, or otherwise verified work.",
  },
  {
    value: "closed",
    label: "Closed",
    description: "Archived or closed work that should not re-enter execution.",
  },
] as const;

const PRIORITIES = [
  { value: "P0", label: "Critical" },
  { value: "P1", label: "High" },
  { value: "P2", label: "Medium" },
  { value: "P3", label: "Low" },
  { value: "P4", label: "Later" },
] as const;

function compact(value: string): string | undefined {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function labelsFromText(value: string): string[] {
  return value
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean);
}

function groupByStatus(items: WorkUnit[]) {
  return STATUS_COLUMNS.reduce<Record<string, WorkUnit[]>>((acc, column) => {
    acc[column.value] = items.filter((item) => item.status === column.value);
    return acc;
  }, {});
}

function statusLabel(status: string) {
  return STATUS_COLUMNS.find((column) => column.value === status)?.label ?? status;
}

function priorityLabel(priority: string) {
  return PRIORITIES.find((item) => item.value === priority)?.label ?? priority;
}

function agentOptionsFromDeerFlow(agents: Array<{ name: string }>) {
  const seen = new Set<string>();
  return [{ name: LEAD_AGENT_NAME }, ...agents].filter((agent) => {
    if (seen.has(agent.name)) return false;
    seen.add(agent.name);
    return true;
  });
}

function isLinked(item: WorkUnit) {
  return Boolean(item.workflow_id ?? item.thread_id ?? item.run_id);
}

function itemNeedsAttention(item: WorkUnit) {
  return item.status === "blocked" || item.status === "review" || item.priority === "P0" || item.priority === "P1";
}

function itemMatchesSearch(item: WorkUnit, search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  return [
    item.work_unit_id,
    item.title,
    item.description,
    item.priority,
    priorityLabel(item.priority),
    item.status,
    item.workflow_id,
    item.thread_id,
    item.run_id,
    item.labels.join(" "),
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(query));
}

function parseBulkLines(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim().replace(/^[-*]\s+/, ""))
    .filter(Boolean);
}

function priorityTone(priority: string) {
  if (priority === "P0" || priority === "P1") return "bg-red-500/10 text-red-600 dark:text-red-300";
  if (priority === "P2") return "bg-amber-500/10 text-amber-600 dark:text-amber-300";
  return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300";
}

function relativeDate(value?: string) {
  if (!value) return "not updated";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return value;
  const days = Math.max(0, Math.floor((Date.now() - time) / 86_400_000));
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}

export default function WorkPage() {
  const { data: modules } = useModuleFlags();
  const workApiEnabled = modules
    ? modules.work.enabled && modules.work.api_enabled
    : true;
  const { data: items = [], error } = useWorkUnits({
    enabled: workApiEnabled,
  });
  const { agents } = useAgents();
  const createWorkUnit = useCreateWorkUnit();
  const updateWorkUnit = useUpdateWorkUnit();
  const agentOptions = useMemo(() => agentOptionsFromDeerFlow(agents), [agents]);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [priority, setPriority] = useState("P2");
  const [assigneeRef, setAssigneeRef] = useState(LEAD_AGENT_NAME);
  const [labels, setLabels] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [assigneeFilter, setAssigneeFilter] = useState("all");
  const [attentionFilter, setAttentionFilter] = useState("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [collapsedColumns, setCollapsedColumns] = useState<Record<string, boolean>>({});
  const [detailPanelOpen, setDetailPanelOpen] = useState(true);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      if (priorityFilter !== "all" && item.priority !== priorityFilter) return false;
      if (assigneeFilter === "unassigned" && item.assignee_ref) return false;
      if (
        assigneeFilter !== "all" &&
        assigneeFilter !== "unassigned" &&
        item.assignee_ref !== assigneeFilter
      ) {
        return false;
      }
      if (attentionFilter === "attention" && !itemNeedsAttention(item)) return false;
      if (attentionFilter === "runtime" && !isLinked(item)) return false;
      return itemMatchesSearch(item, search);
    });
  }, [assigneeFilter, attentionFilter, items, priorityFilter, search]);

  const columns = useMemo(() => groupByStatus(filteredItems), [filteredItems]);
  const selectedItem =
    filteredItems.find((item) => item.work_unit_id === selectedId) ?? filteredItems[0];
  const blockedCount = items.filter((item) => item.status === "blocked").length;
  const runtimeCount = items.filter(isLinked).length;
  const health = blockedCount > 0 ? "red" : "green";

  const errorMessage =
    (error instanceof Error ? error.message : null) ??
    createWorkUnit.error?.message;

  useEffect(() => {
    if (selectedId && filteredItems.some((item) => item.work_unit_id === selectedId)) return;
    setSelectedId(filteredItems[0]?.work_unit_id ?? null);
  }, [filteredItems, selectedId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!compact(title)) return;
    const created = await createWorkUnit.mutateAsync({
      title: title.trim(),
      description: compact(description),
      status: "backlog",
      priority,
      assignee_ref: assigneeRef === "unassigned" ? undefined : assigneeRef,
      labels: labelsFromText(labels),
    });
    setSelectedId(created.work_unit_id);
    setTitle("");
    setDescription("");
    setAssigneeRef(LEAD_AGENT_NAME);
    setLabels("");
    setPriority("P2");
    setCreateOpen(false);
  }

  async function handleBulkSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const titles = parseBulkLines(bulkText);
    if (titles.length === 0) return;
    let lastCreated: WorkUnit | null = null;
    for (const workTitle of titles) {
      lastCreated = await createWorkUnit.mutateAsync({
        title: workTitle,
        status: "backlog",
        priority,
        assignee_ref: assigneeRef === "unassigned" ? undefined : assigneeRef,
        labels: labelsFromText(labels),
      });
    }
    if (lastCreated) setSelectedId(lastCreated.work_unit_id);
    setBulkText("");
    setAssigneeRef(LEAD_AGENT_NAME);
    setLabels("");
    setPriority("P2");
    setBulkOpen(false);
  }

  function openCreate() {
    setCreateOpen(true);
  }

  function toggleColumn(status: string) {
    setCollapsedColumns((current) => ({
      ...current,
      [status]: !current[status],
    }));
  }

  if (!workApiEnabled) {
    return (
      <WorkspaceContainer>
        <WorkspaceHeader />
        <WorkspaceBody>
          <div className="flex h-full w-full items-center justify-center p-6">
            <div className="max-w-md space-y-2 text-center">
              <h1 className="text-xl font-semibold">Work Module disabled</h1>
              <p className="text-muted-foreground text-sm">
                Enable the Work Module in DeerFlow module config to use this
                workspace surface.
              </p>
            </div>
          </div>
        </WorkspaceBody>
      </WorkspaceContainer>
    );
  }

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="items-stretch">
        <div className="bg-background flex min-h-0 w-full flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <FilterSelect label="Priority" value={priorityFilter} onValueChange={setPriorityFilter}>
              <SelectItem value="all">All priorities</SelectItem>
              {PRIORITIES.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </FilterSelect>
            <FilterSelect label="Attention" value={attentionFilter} onValueChange={setAttentionFilter}>
              <SelectItem value="all">All attention</SelectItem>
              <SelectItem value="attention">Needs attention</SelectItem>
              <SelectItem value="runtime">Runtime linked</SelectItem>
            </FilterSelect>
            <FilterSelect label="Agent" value={assigneeFilter} onValueChange={setAssigneeFilter}>
              <SelectItem value="all">All agents</SelectItem>
              {agentOptions.map((agent) => (
                <SelectItem key={agent.name} value={agent.name}>
                  {agent.name}
                </SelectItem>
              ))}
              <SelectItem value="unassigned">Unassigned</SelectItem>
            </FilterSelect>
            <div className="relative min-w-60 flex-1">
              <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" />
              <Input
                aria-label="Search work units"
                className="h-9 pl-9"
                placeholder="Search work unit, workflow, run"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <Button aria-label="New Work Unit" type="button" size="sm" onClick={() => openCreate()}>
              <PlusIcon />
              New
            </Button>
            <Button aria-label="Bulk capture Work Units" type="button" size="sm" variant="outline" onClick={() => setBulkOpen(true)}>
              <ListPlus />
              Bulk
            </Button>
            {errorMessage && <div className="text-destructive basis-full text-sm">{errorMessage}</div>}
          </div>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle>New Work Unit</DialogTitle>
                <DialogDescription>
                  Capture a backlog unit for an agent or runtime to pick up.
                </DialogDescription>
              </DialogHeader>
              <form className="grid gap-4" onSubmit={(event) => void handleSubmit(event)}>
                <div className="grid gap-2">
                  <label className="text-sm font-medium" htmlFor="work-title">
                    Title
                  </label>
                  <Input
                    id="work-title"
                    placeholder="Short work unit title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium" htmlFor="work-description">
                    Next action / description
                  </label>
                  <Textarea
                    id="work-description"
                    className="min-h-24 resize-none"
                    placeholder="What should happen next?"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="grid gap-2">
                    <label className="text-sm font-medium">Priority</label>
                    <Select value={priority} onValueChange={setPriority}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PRIORITIES.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <label className="text-sm font-medium">Agent</label>
                    <Select value={assigneeRef} onValueChange={setAssigneeRef}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {agentOptions.map((agent) => (
                          <SelectItem key={agent.name} value={agent.name}>
                            {agent.name}
                          </SelectItem>
                        ))}
                        <SelectItem value="unassigned">Unassigned</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid gap-2">
                  <label className="text-sm font-medium" htmlFor="work-tags">
                    Tags
                  </label>
                  <Input
                    id="work-tags"
                    placeholder="customer, review, incident"
                    value={labels}
                    onChange={(event) => setLabels(event.target.value)}
                  />
                </div>
                {errorMessage && <div className="text-destructive text-sm">{errorMessage}</div>}
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={createWorkUnit.isPending || !compact(title)}>
                    <PlusIcon />
                    Create Work Unit
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
          <Dialog open={bulkOpen} onOpenChange={setBulkOpen}>
            <DialogContent className="max-h-[86vh] overflow-y-auto sm:max-w-2xl">
              <DialogHeader>
                <DialogTitle>Bulk Capture Work Units</DialogTitle>
                <DialogDescription>
                  Paste one work unit title per line. New units start in backlog.
                </DialogDescription>
              </DialogHeader>
              <form className="grid gap-4" onSubmit={(event) => void handleBulkSubmit(event)}>
                <div className="grid gap-2">
                  <label className="text-sm font-medium" htmlFor="work-bulk">
                    Work units
                  </label>
                  <Textarea
                    id="work-bulk"
                    className="min-h-52 resize-none font-mono text-sm"
                    placeholder={"PR 1: Durable workflow docs\nPR 2: Workflow store\nPR 3: Workflow APIs"}
                    value={bulkText}
                    onChange={(event) => setBulkText(event.target.value)}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="grid gap-2">
                    <label className="text-sm font-medium">Priority</label>
                    <Select value={priority} onValueChange={setPriority}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {PRIORITIES.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <label className="text-sm font-medium">Agent</label>
                    <Select value={assigneeRef} onValueChange={setAssigneeRef}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {agentOptions.map((agent) => (
                          <SelectItem key={agent.name} value={agent.name}>
                            {agent.name}
                          </SelectItem>
                        ))}
                        <SelectItem value="unassigned">Unassigned</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <label className="text-sm font-medium" htmlFor="work-bulk-tags">
                      Tags
                    </label>
                    <Input
                      id="work-bulk-tags"
                      placeholder="upstream, pr-stack"
                      value={labels}
                      onChange={(event) => setLabels(event.target.value)}
                    />
                  </div>
                </div>
                {errorMessage && <div className="text-destructive text-sm">{errorMessage}</div>}
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setBulkOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={createWorkUnit.isPending || parseBulkLines(bulkText).length === 0}>
                    <ListPlus />
                    Create {parseBulkLines(bulkText).length || ""} Work Units
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
          <div
            className={`grid min-h-0 flex-1 ${
              detailPanelOpen
                ? "grid-cols-[minmax(0,1fr)_minmax(320px,380px)]"
                : "grid-cols-[minmax(0,1fr)_44px]"
            }`}
          >
            <div className="min-h-0 overflow-x-auto overflow-y-hidden border-r">
              <main className="flex min-w-max gap-3 p-4 pb-7">
                {STATUS_COLUMNS.map((column) => {
                  const collapsed = Boolean(collapsedColumns[column.value]);
                  const columnItems = columns[column.value] ?? [];

                  return (
                    <section
                      key={column.value}
                      className={`bg-muted/15 flex min-h-[560px] min-w-0 flex-col rounded-md border transition-[width] duration-200 ${
                        collapsed ? "w-14 shrink-0" : "w-[260px] shrink-0"
                      }`}
                    >
                      <div className="border-b px-3 py-2">
                        {collapsed ? (
                          <div className="flex min-h-32 flex-col items-center gap-3">
                            <Button
                              aria-label={`Expand ${column.label}`}
                              variant="ghost"
                              size="icon"
                              className="size-7"
                              onClick={() => toggleColumn(column.value)}
                            >
                              <ChevronRight />
                            </Button>
                            <Badge variant="secondary">{columnItems.length}</Badge>
                            <div className="text-muted-foreground rotate-180 [writing-mode:vertical-rl] text-xs font-semibold">
                              {column.label}
                            </div>
                          </div>
                        ) : (
                          <div className="flex h-7 items-center gap-2">
                            <Button
                              aria-label={`Collapse ${column.label}`}
                              variant="ghost"
                              size="icon"
                              className="size-7 shrink-0"
                              onClick={() => toggleColumn(column.value)}
                            >
                              <ChevronDown />
                            </Button>
                            <div
                              className="min-w-0 flex-1 truncate text-sm font-semibold"
                              title={column.description}
                            >
                              {column.label}
                            </div>
                            <Badge variant="secondary" className="shrink-0">
                              {columnItems.length}
                            </Badge>
                            {column.value === "backlog" && (
                              <Button
                                aria-label="Create in Backlog"
                                variant="ghost"
                                size="icon"
                                className="size-7 shrink-0"
                                onClick={openCreate}
                              >
                                <PlusIcon />
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                      {!collapsed && (
                        <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
                          {columnItems.length === 0 && (
                            <div className="text-muted-foreground flex h-20 items-center justify-center rounded-md border border-dashed text-xs">
                              No work units
                            </div>
                          )}
                          {columnItems.map((item) => (
                            <WorkUnitCard
                              key={item.work_unit_id}
                              item={item}
                              selected={item.work_unit_id === selectedItem?.work_unit_id}
                              onSelect={() => {
                                setSelectedId(item.work_unit_id);
                                setDetailPanelOpen(true);
                              }}
                            />
                          ))}
                        </div>
                      )}
                    </section>
                  );
                })}
              </main>
            </div>
            <WorkUnitDetailPanel
              item={selectedItem}
              agents={agentOptions}
              collapsed={!detailPanelOpen}
              onToggle={() => setDetailPanelOpen((current) => !current)}
              onAssign={(workUnitId, nextAssignee) =>
                updateWorkUnit.mutate({
                  workUnitId,
                  request: {
                    assignee_ref: nextAssignee === "unassigned" ? null : nextAssignee,
                  },
                })
              }
            />
          </div>
          <div className="text-muted-foreground flex h-8 shrink-0 items-center gap-4 border-t px-4 text-xs">
            <span>
              Attention <strong className="text-foreground">{blockedCount}</strong>
            </span>
            <span>
              Health <strong className={health === "red" ? "text-red-500" : "text-emerald-500"}>{health}</strong>
            </span>
            <span>
              Runtimes <strong className="text-emerald-500">{runtimeCount}</strong>
            </span>
            <span>Live gateway</span>
          </div>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}

function FilterSelect({
  label,
  value,
  onValueChange,
  children,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className="h-9 w-44 justify-between">
        <span className="text-muted-foreground text-[11px] font-semibold uppercase">{label}</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>{children}</SelectContent>
    </Select>
  );
}

function WorkUnitCard({
  item,
  selected,
  onSelect,
}: {
  item: WorkUnit;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <article
      className={`bg-background flex min-h-56 cursor-pointer flex-col gap-3 rounded-md border p-3 text-left shadow-xs transition-colors ${
        selected ? "border-primary/70 ring-primary/20 ring-2" : "hover:border-primary/50"
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-muted-foreground flex items-center gap-2 text-[11px] font-semibold uppercase">
            <span className="truncate">{item.work_unit_id.slice(0, 12)}</span>
            <span>Work Unit</span>
          </div>
          <div className="mt-1 line-clamp-3 text-sm font-semibold leading-snug">{item.title}</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        <Badge variant="secondary">{statusLabel(item.status)}</Badge>
        <Badge variant="outline" className={priorityTone(item.priority)}>
          {priorityLabel(item.priority)}
        </Badge>
        <Badge variant="outline">
          {item.status === "done" || item.status === "closed"
            ? "Verified"
            : item.status === "backlog"
              ? "Planned"
              : "Agent managed"}
        </Badge>
      </div>
      {item.description && (
        <div className="bg-muted/25 rounded-md border p-2">
          <div className="text-muted-foreground text-[11px] font-semibold uppercase">Next action</div>
          <div className="mt-1 line-clamp-3 text-xs font-medium leading-snug">{item.description}</div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-1 text-[11px]">
        <MetricChip label="Tags" value={item.labels.length} />
        <MetricChip label="Gates" value={item.status === "blocked" ? 1 : 0} />
        <MetricChip label="Review" value={item.status === "review" ? "needed" : "not reviewed"} />
        <MetricChip label="Updated" value={relativeDate(item.updated_at)} />
      </div>
      <div className="mt-auto flex flex-wrap gap-1">
        {item.assignee_ref && <Badge variant="secondary">agent: {item.assignee_ref}</Badge>}
        {isLinked(item) && <Badge variant="secondary">runtime linked</Badge>}
        {item.labels.slice(0, 2).map((label) => (
          <Badge key={label} variant="outline">
            {label}
          </Badge>
        ))}
        {itemNeedsAttention(item) && <Badge variant="outline">attention</Badge>}
      </div>
    </article>
  );
}

function MetricChip({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-muted/20 rounded border px-2 py-1">
      <span className="text-muted-foreground">{label}</span>{" "}
      <strong className="font-medium">{value}</strong>
    </div>
  );
}

function WorkUnitDetailPanel({
  item,
  agents,
  collapsed,
  onToggle,
  onAssign,
}: {
  item?: WorkUnit;
  agents: Array<{ name: string }>;
  collapsed: boolean;
  onToggle: () => void;
  onAssign: (workUnitId: string, assigneeRef: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<"overview" | "chat" | "trace">("overview");

  if (collapsed) {
    return (
      <aside className="bg-background flex min-h-0 flex-col items-center border-l">
        <Button
          aria-label="Show detail panel"
          type="button"
          variant="ghost"
          size="icon"
          className="mt-3 size-8"
          onClick={onToggle}
        >
          <PanelRightOpen />
        </Button>
        <div className="text-muted-foreground mt-4 rotate-180 [writing-mode:vertical-rl] text-xs font-semibold">
          Panel
        </div>
      </aside>
    );
  }

  return (
    <aside className="bg-background flex min-h-0 flex-col">
      <div className="flex h-12 items-center justify-between border-b px-4">
        <div className="flex min-w-0 items-center gap-1">
          <Button
            type="button"
            variant={activeTab === "overview" ? "secondary" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setActiveTab("overview")}
          >
            <FileText />
            Overview
          </Button>
          <Button
            type="button"
            variant={activeTab === "chat" ? "secondary" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setActiveTab("chat")}
          >
            <MessageSquare />
            Chat
          </Button>
          <Button
            type="button"
            variant={activeTab === "trace" ? "secondary" : "ghost"}
            size="sm"
            className="h-8"
            onClick={() => setActiveTab("trace")}
          >
            <Activity />
            Trace
          </Button>
        </div>
        <Button aria-label="Hide detail panel" type="button" variant="ghost" size="icon" onClick={onToggle}>
          <PanelRightClose />
        </Button>
      </div>
      {activeTab === "chat" ? (
        <WorkUnitChatPanel agents={agents} item={item} />
      ) : activeTab === "trace" ? (
        <WorkUnitTracePanel item={item} />
      ) : !item ? (
          <div className="text-muted-foreground flex flex-1 items-center justify-center p-6 text-center text-sm">
            Select a Work Unit
          </div>
        ) : (
          <ScrollArea className="min-h-0 flex-1">
            <div className="space-y-4 p-4">
              <div>
                <div className="text-muted-foreground text-[11px] font-semibold uppercase">{item.work_unit_id}</div>
                <h2 className="mt-1 text-base font-semibold leading-snug">{item.title}</h2>
                {item.description && <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{item.description}</p>}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <InfoCell label="Status" value={statusLabel(item.status)} />
                <InfoCell label="Priority" value={priorityLabel(item.priority)} />
                <InfoCell label="Source" value={item.source ?? item.source_type} />
                <InfoCell label="Updated" value={relativeDate(item.updated_at)} />
              </div>
              <section className="space-y-2">
                <div className="text-muted-foreground text-[11px] font-semibold uppercase">
                  Assignment
                </div>
                <Select
                  value={item.assignee_ref ?? "unassigned"}
                  onValueChange={(value) => onAssign(item.work_unit_id, value)}
                >
                  <SelectTrigger aria-label="Assigned agent">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {agents.map((agent) => (
                      <SelectItem key={agent.name} value={agent.name}>
                        {agent.name}
                      </SelectItem>
                    ))}
                    <SelectItem value="unassigned">Unassigned</SelectItem>
                  </SelectContent>
                </Select>
              </section>
              <section className="space-y-2">
                <div className="text-muted-foreground text-[11px] font-semibold uppercase">Runtime refs</div>
                <RefRow label="workflow_id" value={item.workflow_id} />
                <RefRow label="thread_id" value={item.thread_id} />
                <RefRow label="run_id" value={item.run_id} />
                <div className="flex flex-wrap gap-2 pt-1">
                  {item.thread_id && (
                    <Button asChild variant="outline" size="sm">
                      <Link href={`/workspace/chats/${item.thread_id}`}>Open chat</Link>
                    </Button>
                  )}
                  {item.workflow_id && (
                    <Button type="button" variant="outline" size="sm" onClick={() => setActiveTab("trace")}>
                      Trace
                      <Activity />
                    </Button>
                  )}
                </div>
              </section>
              <section className="space-y-2">
                <div className="text-muted-foreground text-[11px] font-semibold uppercase">Tags</div>
                <div className="flex flex-wrap gap-1">
                  {item.labels.length > 0 ? (
                    item.labels.map((label) => (
                      <Badge key={label} variant="secondary">
                        {label}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-muted-foreground text-sm">No tags</span>
                  )}
                </div>
              </section>
            </div>
          </ScrollArea>
        )}
    </aside>
  );
}

function InfoCell({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="bg-muted/20 min-w-0 rounded-md border p-2">
      <div className="text-muted-foreground text-[11px] font-semibold uppercase">{label}</div>
      <div className="mt-1 truncate text-sm font-medium">{value ?? "-"}</div>
    </div>
  );
}

function RefRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="bg-muted/20 grid grid-cols-[86px_minmax(0,1fr)] gap-2 rounded-md border p-2 text-xs">
      <span className="text-muted-foreground font-semibold">{label}</span>
      <span className="truncate font-mono">{value ?? "-"}</span>
    </div>
  );
}

"use client";

import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { WorkUnit } from "@/core/work-units";
import {
  fetchWorkflowTimeline,
  type WorkflowTimelineEvent,
} from "@/core/workflows/api";

function relativeDate(value?: string | null) {
  if (!value) return "-";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return value;
  const days = Math.max(0, Math.floor((Date.now() - time) / 86_400_000));
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}

function formatTraceContent(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.length > 700 ? `${value.slice(0, 700)}...` : value;
  try {
    const text = JSON.stringify(value, null, 2);
    return text.length > 700 ? `${text.slice(0, 700)}...` : text;
  } catch {
    return Object.prototype.toString.call(value);
  }
}

function RefRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="bg-muted/20 grid grid-cols-[86px_minmax(0,1fr)] gap-2 rounded-md border p-2 text-xs">
      <span className="text-muted-foreground font-semibold">{label}</span>
      <span className="truncate font-mono">{value ?? "-"}</span>
    </div>
  );
}

function TraceEventCard({ event }: { event: WorkflowTimelineEvent }) {
  const content = formatTraceContent(event.content ?? event.metadata);

  return (
    <article className="bg-muted/15 rounded-md border p-3 text-xs">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold leading-snug">{event.event_type}</div>
          <div className="text-muted-foreground mt-1 truncate">
            {event.created_at ? relativeDate(event.created_at) : "undated"}
            {typeof event.seq === "number" ? ` · seq ${event.seq}` : ""}
          </div>
        </div>
        <Badge variant="outline" className="shrink-0">
          {event.kind === "workflow_event" ? "Workflow" : "Run"}
        </Badge>
      </div>
      {event.category && (
        <div className="text-muted-foreground mt-2 font-medium uppercase">{event.category}</div>
      )}
      {content && (
        <pre className="bg-background/70 text-muted-foreground mt-2 max-h-32 overflow-auto rounded border p-2 font-mono text-[11px] whitespace-pre-wrap">
          {content}
        </pre>
      )}
    </article>
  );
}

export function WorkUnitTracePanel({ item }: { item?: WorkUnit }) {
  const workflowId = item?.workflow_id;
  const traceQuery = useQuery({
    queryKey: ["workflow-timeline", workflowId],
    queryFn: () => fetchWorkflowTimeline(workflowId!),
    enabled: Boolean(workflowId),
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });

  if (!item) {
    return (
      <div className="text-muted-foreground flex flex-1 items-center justify-center p-6 text-center text-sm">
        Select a Work Unit
      </div>
    );
  }

  if (!workflowId) {
    return (
      <div className="text-muted-foreground flex flex-1 items-center justify-center p-6 text-center text-sm">
        No workflow trace is linked to this Work Unit yet.
      </div>
    );
  }

  const events = traceQuery.data?.timeline ?? [];

  return (
    <ScrollArea className="min-h-0 flex-1">
      <div className="space-y-4 p-4">
        <div className="space-y-2">
          <div className="text-muted-foreground text-[11px] font-semibold uppercase">Workflow trace</div>
          <RefRow label="workflow_id" value={workflowId} />
          <RefRow label="run_id" value={item.run_id} />
        </div>
        {traceQuery.isLoading ? (
          <div className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
            Loading trace...
          </div>
        ) : traceQuery.error ? (
          <div className="text-destructive rounded-md border p-3 text-sm">
            {traceQuery.error instanceof Error ? traceQuery.error.message : "Failed to load trace"}
          </div>
        ) : events.length === 0 ? (
          <div className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
            No trace events yet.
          </div>
        ) : (
          <div className="space-y-2">
            {events.map((event, index) => (
              <TraceEventCard key={`${event.kind}-${event.seq ?? index}-${event.event_type}`} event={event} />
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  );
}

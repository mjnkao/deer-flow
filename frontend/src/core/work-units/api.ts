import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type WorkUnit = {
  work_unit_id: string;
  title: string;
  description?: string | null;
  status: string;
  priority: string;
  assignee_ref?: string | null;
  reporter_ref?: string | null;
  due_at?: string | null;
  workflow_id?: string | null;
  thread_id?: string | null;
  run_id?: string | null;
  source_type: string;
  source?: string | null;
  external_type?: string | null;
  external_ref?: string | null;
  external_url?: string | null;
  labels: string[];
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export type CreateWorkUnitRequest = {
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  assignee_ref?: string;
  reporter_ref?: string;
  due_at?: string;
  workflow_id?: string;
  thread_id?: string;
  run_id?: string;
  source_type?: string;
  source?: string;
  external_type?: string;
  external_ref?: string;
  external_url?: string;
  labels?: string[];
  metadata?: Record<string, unknown>;
  work_unit_id?: string;
};

export type UpdateWorkUnitRequest = Partial<
  Pick<
    WorkUnit,
    | "title"
    | "description"
    | "status"
    | "priority"
    | "assignee_ref"
    | "reporter_ref"
    | "due_at"
    | "workflow_id"
    | "thread_id"
    | "run_id"
    | "source_type"
    | "source"
    | "external_type"
    | "external_ref"
    | "external_url"
    | "labels"
    | "metadata"
  >
>;

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String(payload.detail)
        : `Request failed with ${response.status}`;
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function listWorkUnits(params: {
  status?: string;
  limit?: number;
} = {}): Promise<WorkUnit[]> {
  const search = new URLSearchParams();
  if (params.status) search.set("status", params.status);
  if (params.limit) search.set("limit", String(params.limit));
  const query = search.toString();
  const response = await fetch(
    `${getBackendBaseURL()}/api/work-units${query ? `?${query}` : ""}`,
  );
  const payload = await readJson<{ data: WorkUnit[] }>(response);
  return payload.data;
}

export async function createWorkUnit(
  request: CreateWorkUnitRequest,
): Promise<WorkUnit> {
  const response = await fetch(`${getBackendBaseURL()}/api/work-units`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return readJson<WorkUnit>(response);
}

export async function updateWorkUnit(
  workUnitId: string,
  request: UpdateWorkUnitRequest,
): Promise<WorkUnit> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/work-units/${encodeURIComponent(workUnitId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    },
  );
  return readJson<WorkUnit>(response);
}

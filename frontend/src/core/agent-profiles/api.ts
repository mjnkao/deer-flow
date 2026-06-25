import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type AgentProfileLanguage = "markdown" | "yaml" | "json";

export interface AgentProfileFileSummary {
  id: string;
  label: string;
  path: string;
  kind: string;
  language: AgentProfileLanguage;
  scope: string;
  agent_ref?: string | null;
  editable: boolean;
  exists: boolean;
  size?: number | null;
  updated_at?: number | null;
}

export interface AgentProfileFile extends AgentProfileFileSummary {
  content: string;
}

export interface AgentProfileSkills {
  agent_ref: string;
  editable: boolean;
  inherited: boolean;
  source: string;
  skills: string[] | null;
}

async function parseError(response: Response, fallback: string) {
  const payload = (await response.json().catch(() => ({}))) as {
    detail?: string;
  };
  return payload.detail ?? fallback;
}

export async function listAgentProfileFiles(): Promise<
  AgentProfileFileSummary[]
> {
  const res = await fetch(`${getBackendBaseURL()}/api/agent-profile-files`);
  if (!res.ok) {
    throw new Error(
      await parseError(res, `Failed to load profile files: ${res.statusText}`),
    );
  }
  const data = (await res.json()) as { files: AgentProfileFileSummary[] };
  return data.files;
}

export async function getAgentProfileFile(
  id: string,
): Promise<AgentProfileFile> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agent-profile-files/${encodeURIComponent(id)}`,
  );
  if (!res.ok) {
    throw new Error(
      await parseError(res, `Failed to load profile file: ${res.statusText}`),
    );
  }
  return res.json() as Promise<AgentProfileFile>;
}

export async function updateAgentProfileFile(
  id: string,
  content: string,
): Promise<AgentProfileFile> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agent-profile-files/${encodeURIComponent(id)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
  if (!res.ok) {
    throw new Error(
      await parseError(res, `Failed to save profile file: ${res.statusText}`),
    );
  }
  return res.json() as Promise<AgentProfileFile>;
}

export async function getAgentProfileSkills(
  agentRef: string,
): Promise<AgentProfileSkills> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agent-profile-skills/${encodeURIComponent(agentRef)}`,
  );
  if (!res.ok) {
    throw new Error(
      await parseError(res, `Failed to load agent skills: ${res.statusText}`),
    );
  }
  return res.json() as Promise<AgentProfileSkills>;
}

export async function updateAgentProfileSkills(
  agentRef: string,
  skills: string[] | null,
): Promise<AgentProfileSkills> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/agent-profile-skills/${encodeURIComponent(agentRef)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skills }),
    },
  );
  if (!res.ok) {
    throw new Error(
      await parseError(res, `Failed to save agent skills: ${res.statusText}`),
    );
  }
  return res.json() as Promise<AgentProfileSkills>;
}

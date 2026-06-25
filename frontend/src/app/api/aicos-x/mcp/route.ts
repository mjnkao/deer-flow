import type { NextRequest } from "next/server";

const AICOS_X_MCP_URL =
  process.env.AICOS_X_MCP_URL ?? "http://127.0.0.1:37031/mcp";

const PROTECTED_AICOS_WRITE_TOOLS = new Set([
  "aicos_contract_create",
  "aicos_contract_update",
  "aicos_outcome_create",
  "aicos_outcome_update",
  "aicos_attempt_create",
  "aicos_attempt_update",
  "aicos_evidence_create",
  "aicos_blocker_create",
  "aicos_human_request_create",
  "aicos_delivery_record",
  "aicos_workflow_start",
  "aicos_workflow_resume",
  "aicos_start_work",
  "aicos_start_workflow",
  "aicos_resume_workflow",
  "aicos_work_unit_create",
  "aicos_work_unit_update",
  "aicos_work_criterion_upsert",
  "aicos_context_packet_create",
  "aicos_runtime_invocation_start",
  "aicos_runtime_invocation_update",
  "aicos_runtime_event_record",
  "aicos_gate_open",
  "aicos_gate_resolve",
  "aicos_artifact_record",
  "aicos_evidence_record",
  "aicos_work_review_record",
]);

function protectedWriteToolName(body: unknown) {
  if (!body || typeof body !== "object") return "";
  const params = (body as { params?: { name?: unknown } }).params;
  const name = params?.name;
  return typeof name === "string" && PROTECTED_AICOS_WRITE_TOOLS.has(name)
    ? name
    : "";
}

function guardedResponse(id: unknown, toolName: string) {
  return Response.json(
    {
      jsonrpc: "2.0",
      id: id ?? 1,
      error: {
        code: 423,
        message: `Protected AICOS-X write ${toolName} is blocked by the DeerFlow dashboard boundary.`,
      },
    },
    { status: 423 },
  );
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { ok: false, error_code: "invalid_json", message: "Invalid JSON body" },
      { status: 400 },
    );
  }

  const blockedTool = protectedWriteToolName(body);
  if (blockedTool) {
    return guardedResponse((body as { id?: unknown }).id, blockedTool);
  }

  try {
    const response = await fetch(AICOS_X_MCP_URL, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    return new Response(await response.arrayBuffer(), {
      status: response.status,
      headers: {
        "content-type":
          response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        error_code: "aicos_x_unavailable",
        message: error instanceof Error ? error.message : "AICOS-X unavailable",
      },
      { status: 503 },
    );
  }
}

"""AICOS-X dashboard boundary for the DeerFlow workspace."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.gateway.deps import get_checkpointer, get_run_manager, get_stream_bridge
from app.gateway.routers.thread_runs import RunCreateRequest
from app.gateway.services import start_run, wait_for_run_completion
from deerflow.runtime import serialize_channel_values_for_api

router = APIRouter(prefix="/api/aicos-x", tags=["aicos-x"])

DEFAULT_AICOS_X_MCP_URL = "http://127.0.0.1:37031/mcp"
PROTECTED_AICOS_WRITE_TOOLS = {
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
}


class AicosActor(BaseModel):
    actor_ref: str = "deerflow-dashboard"
    runtime: str = "deerflow"
    role: str = "operator"


class StartWorkRequest(BaseModel):
    operating_scope_key: str = "aicos-x"
    title: str = Field(..., min_length=1)
    objective: str | None = None
    instructions: str | None = None
    next_action: str | None = None
    priority: str | None = None
    assigned_agent_ref: str | None = None
    upload_thread_id: str | None = None
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)
    owner_ref: str | None = None
    selected_work_ref: str | None = None
    dry_run: bool = False
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatTurnRequest(BaseModel):
    operating_scope_key: str = "aicos-x"
    message: str = Field(..., min_length=1)
    owner_ref: str | None = None
    agentId: str | None = None
    agentRef: str | None = None
    selected_work_ref: str | None = None
    workItemId: str | None = None
    model: str | None = None
    mode: str | None = None
    thinking: str | None = None
    thread_id: str | None = None
    subagent_enabled: bool | None = None
    max_concurrent_subagents: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _mcp_url() -> str:
    return os.environ.get("AICOS_X_MCP_URL", DEFAULT_AICOS_X_MCP_URL)


def _health_url() -> str:
    url = _mcp_url()
    return url[:-4] + "/health" if url.endswith("/mcp") else url.rstrip("/") + "/health"


def _protected_write_tool_name(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    params = body.get("params")
    if not isinstance(params, dict):
        return ""
    name = params.get("name")
    return name if isinstance(name, str) and name in PROTECTED_AICOS_WRITE_TOOLS else ""


def _actor(request: Request, *, fallback_ref: str = "deerflow-dashboard") -> dict[str, str]:
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    return {
        "actor_ref": str(user_id or fallback_ref),
        "runtime": "deerflow",
        "role": getattr(user, "system_role", None) or "operator",
    }


def _resolve_owner_ref(requested_owner_ref: str | None, actor: dict[str, str]) -> str:
    """Resolve Work Unit owner from the gateway boundary, not from agent output."""
    configured = {item.strip() for item in os.environ.get("AICOS_X_ALLOWED_OWNER_REFS", "aicos-x").split(",") if item.strip()}
    allowed = configured | {actor["actor_ref"]}
    owner_ref = (requested_owner_ref or "aicos-x").strip()
    if owner_ref not in allowed:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "aicos_x_owner_ref_not_allowed",
                "message": "owner_ref must come from AICOS-X owner registry or the authenticated DeerFlow actor.",
                "owner_ref": owner_ref,
                "allowed_owner_refs": sorted(allowed),
            },
        )
    return owner_ref


async def _call_mcp_tool(name: str, arguments: dict[str, Any], *, timeout: float = 45) -> dict[str, Any]:
    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _mcp_url(),
                json=body,
                headers={"accept": "application/json", "content-type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "aicos_x_unavailable", "message": str(exc)},
        ) from exc
    try:
        rpc = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "aicos_x_non_json", "message": response.text[:500]},
        ) from exc
    if response.status_code >= 400 or rpc.get("error"):
        raise HTTPException(status_code=response.status_code if response.status_code >= 400 else 502, detail=rpc.get("error") or rpc)
    text = (rpc.get("result") or {}).get("content", [{}])[0].get("text")
    if not text:
        raise HTTPException(status_code=502, detail={"code": "aicos_x_empty_tool_response", "tool": name})
    try:
        result = httpx.Response(200, content=text).json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail={"code": "aicos_x_tool_non_json", "tool": name}) from exc
    if result.get("ok") is False:
        raise HTTPException(status_code=409, detail=result)
    return result


def _criteria(body: StartWorkRequest) -> list[dict[str, Any]]:
    criteria = body.acceptance_criteria or []
    required_evidence = body.required_evidence or []
    if not criteria and required_evidence:
        criteria = required_evidence
    return [
        {
            "criterion_key": f"AC-{index + 1}",
            "description": text,
            "evidence_required": True,
            "required_evidence_type": required_evidence[index] if index < len(required_evidence) else "agent_result",
        }
        for index, text in enumerate(criteria)
        if text.strip()
    ]


def _uploaded_file_source_refs(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for file in files:
        filename = file.get("filename") or file.get("path") or file.get("virtual_path")
        if not filename:
            continue
        ref = file.get("markdown_virtual_path") or file.get("virtual_path") or file.get("path") or filename
        refs.append(
            {
                "kind": "upload",
                "ref": str(ref),
                "summary": str(filename),
                "metadata": {
                    key: value
                    for key, value in file.items()
                    if key
                    in {
                        "filename",
                        "size",
                        "virtual_path",
                        "artifact_url",
                        "markdown_file",
                        "markdown_virtual_path",
                        "markdown_artifact_url",
                    }
                },
            }
        )
    return refs


def _message_text(message: Any) -> str:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            elif item:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content or "")


def _last_assistant_message(state: dict[str, Any]) -> str:
    messages = state.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        role = message.get("type") or message.get("role") if isinstance(message, dict) else getattr(message, "type", None)
        if role in {"ai", "assistant"}:
            text = _message_text(message).strip()
            if text:
                return text
    return ""


@router.get("/health")
async def health() -> Any:
    """Proxy AICOS-X MCP health through the authenticated DeerFlow gateway."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_health_url(), headers={"accept": "application/json"})
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "aicos_x_unavailable", "message": str(exc)},
        ) from exc
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "aicos_x_non_json", "message": response.text[:500]},
        ) from exc


@router.get("/safety")
async def safety() -> Any:
    """Describe the AICOS-X dashboard command boundary."""
    return {
        "aicos": {
            "mcpEndpointConfigured": True,
            "tokenConfigured": True,
            "tokenSource": "deerflow-session",
        },
        "writes": {
            "mode": "typed_gateway_only",
            "protectedWritesEnabled": True,
            "requiredGate": "DEERFLOW-AICOS-X-TYPED-GATEWAY",
        },
    }


@router.get("/projection")
async def projection() -> Any:
    """Read the native AICOS-X Work Unit dashboard projection."""
    return await _call_mcp_tool("aicos_status_projection", {"operating_scope_key": "aicos-x"})


@router.post("/mcp")
async def mcp(request: Request) -> Any:
    """Proxy JSON-RPC MCP calls while blocking protected dashboard writes."""
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_json"}) from exc

    blocked_tool = _protected_write_tool_name(body)
    if blocked_tool:
        raise HTTPException(
            status_code=423,
            detail={
                "code": "aicos_x_write_blocked",
                "message": f"Protected AICOS-X write {blocked_tool} is blocked by the DeerFlow dashboard boundary.",
            },
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                _mcp_url(),
                json=body,
                headers={"accept": "application/json", "content-type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "aicos_x_unavailable", "message": str(exc)},
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "aicos_x_non_json", "message": response.text[:500]},
        ) from exc


@router.post("/start-work")
async def start_work(body: StartWorkRequest, request: Request) -> Any:
    """Create an AICOS-X Work Unit from the DeerFlow workspace."""
    actor = _actor(request)
    owner_ref = _resolve_owner_ref(body.owner_ref, actor)
    if body.dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "operating_scope_key": body.operating_scope_key,
            "would_call": "aicos_work_unit_create",
        }

    work = await _call_mcp_tool(
        "aicos_work_unit_create",
        {
            "operating_scope_key": body.operating_scope_key,
            "idempotency_key": f"deerflow:start-work:{uuid.uuid4()}",
            "actor": actor,
            "title": body.title,
            "objective": body.objective or body.instructions or body.title,
            "why_this_exists": body.instructions,
            "status": "captured",
            "priority": body.priority,
            "owner_ref": owner_ref,
            "owner_runtime": "deerflow",
            "next_action": body.next_action or "Triage this captured Work Unit and decide whether it is ready for agent execution.",
            "criteria": _criteria(body),
            "source_system": "deerflow_dashboard",
            "source_ref": body.selected_work_ref,
            "metadata": {
                **body.metadata,
                "assigned_agent_ref": body.assigned_agent_ref or "lead_agent",
                "upload_thread_id": body.upload_thread_id,
                "uploaded_files": body.uploaded_files,
            },
        },
    )
    file_source_refs = _uploaded_file_source_refs(body.uploaded_files)
    packet = await _call_mcp_tool(
        "aicos_context_packet_create",
        {
            "operating_scope_key": body.operating_scope_key,
            "idempotency_key": f"deerflow:start-work-context:{uuid.uuid4()}",
            "actor": actor,
            "work_unit_ref": work["work_unit_ref"],
            "summary": body.instructions or body.objective or body.title,
            "source_refs": [
                {
                    "kind": "message",
                    "ref": "deerflow-dashboard:start-work",
                    "summary": body.title,
                }
            ]
            + file_source_refs,
            "environment_snapshot": {
                "runtime": "deerflow",
                "surface": "workspace_dashboard",
                "assigned_agent_ref": body.assigned_agent_ref or "lead_agent",
                "upload_thread_id": body.upload_thread_id,
                "planning_placement": body.metadata.get("planning_placement"),
            },
        },
    )
    return {
        "ok": True,
        "operating_scope_key": body.operating_scope_key,
        "work_unit_ref": work["work_unit_ref"],
        "work_unit_id": work["work_unit_id"],
        "context_packet_ref": packet["context_packet_ref"],
        "context_packet_id": packet["context_packet_id"],
    }


@router.post("/chat-turn")
async def chat_turn(body: ChatTurnRequest, request: Request) -> Any:
    """Create/bind a Work Unit, run DeerFlow lead agent, and record runtime state."""
    actor = _actor(request)
    owner_ref = _resolve_owner_ref(body.owner_ref, actor)
    work_ref = body.selected_work_ref or body.workItemId
    created_work: dict[str, Any] | None = None
    if not work_ref:
        created_work = await _call_mcp_tool(
            "aicos_work_unit_create",
            {
                "operating_scope_key": body.operating_scope_key,
                "idempotency_key": f"deerflow:chat-work:{uuid.uuid4()}",
                "actor": actor,
                "title": body.message[:96],
                "objective": body.message,
                "owner_ref": owner_ref,
                "owner_runtime": "deerflow",
                "next_action": "Execute through DeerFlow lead agent.",
                "criteria": [
                    {
                        "criterion_key": "AC-1",
                        "description": "DeerFlow returns a useful response or opens a Work Gate with the next needed human input.",
                        "evidence_required": True,
                        "required_evidence_type": "agent_response",
                    }
                ],
                "source_system": "deerflow_dashboard_chat",
                "metadata": body.metadata,
            },
        )
        work_ref = created_work["work_unit_ref"]

    packet = await _call_mcp_tool(
        "aicos_context_packet_create",
        {
            "operating_scope_key": body.operating_scope_key,
            "idempotency_key": f"deerflow:chat-context:{uuid.uuid4()}",
            "actor": actor,
            "work_unit_ref": work_ref,
            "summary": body.message[:500],
            "message_refs": [{"kind": "dashboard_chat", "summary": body.message[:500]}],
            "environment_snapshot": {
                "runtime": "deerflow",
                "agent": body.agentId or body.agentRef or "lead_agent",
                "mode": body.mode or "ultra",
            },
        },
    )

    thread_id = body.thread_id or str(uuid.uuid4())
    requested_agent = body.agentId or body.agentRef
    agent_name = requested_agent if requested_agent and requested_agent != "lead_agent" else None
    mode = body.mode or "ultra"
    prompt = (
        f"AICOS-X Work Unit: {work_ref}\n"
        f"Context Packet: {packet['context_packet_ref']}\n\n"
        "Execute this request as the DeerFlow lead agent. Use subagents when useful, "
        "record concrete outputs, and return a concise status plus next action.\n\n"
        f"User request:\n{body.message}"
    )
    run_body = RunCreateRequest(
        assistant_id=agent_name or "lead_agent",
        input={
            "messages": [
                {
                    "type": "human",
                    "content": [{"type": "text", "text": prompt}],
                    "additional_kwargs": {
                        "aicos_x_work_unit_ref": work_ref,
                        "aicos_x_context_packet_ref": packet["context_packet_ref"],
                    },
                }
            ]
        },
        metadata={
            "source": "aicos-x-dashboard",
            "aicos_x_work_unit_ref": work_ref,
            **body.metadata,
        },
        config={"recursion_limit": 1000},
        context={
            "thread_id": thread_id,
            "mode": mode,
            "model_name": body.model,
            "thinking_enabled": mode != "flash",
            "is_plan_mode": mode in {"pro", "ultra"},
            "subagent_enabled": body.subagent_enabled if body.subagent_enabled is not None else mode == "ultra",
            "max_concurrent_subagents": body.max_concurrent_subagents or 4,
            **({"agent_name": agent_name} if agent_name else {}),
        },
        stream_subgraphs=True,
        stream_mode=["values"],
        on_disconnect="continue",
        multitask_strategy="reject",
    )
    record = await start_run(run_body, thread_id, request)
    invocation = await _call_mcp_tool(
        "aicos_runtime_invocation_start",
        {
            "operating_scope_key": body.operating_scope_key,
            "idempotency_key": f"deerflow:runtime:{record.run_id}",
            "actor": actor,
            "work_unit_ref": work_ref,
            "runtime": "deerflow",
            "runtime_instance_ref": "local-x",
            "runtime_ref": record.run_id,
            "runtime_refs": {"thread_id": thread_id, "run_id": record.run_id},
            "context_packet_id": packet["context_packet_id"],
            "agent_ref": requested_agent or "lead_agent",
            "model_ref": body.model,
            "status": "running",
            "summary": "DeerFlow lead agent run started from AICOS-X dashboard chat.",
        },
    )

    completed = False
    final_state: dict[str, Any] = {}
    error_message: str | None = None
    try:
        bridge = get_stream_bridge(request)
        run_mgr = get_run_manager(request)
        completed = await wait_for_run_completion(bridge, record, request, run_mgr)
        if completed:
            checkpointer = get_checkpointer(request)
            checkpoint_tuple = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
            if checkpoint_tuple is not None:
                checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
                final_state = serialize_channel_values_for_api(checkpoint.get("channel_values", {}))
    except Exception as exc:  # noqa: BLE001 - record failure before surfacing
        error_message = str(exc)
        await _call_mcp_tool(
            "aicos_runtime_invocation_update",
            {
                "operating_scope_key": body.operating_scope_key,
                "idempotency_key": f"deerflow:runtime-failed:{record.run_id}",
                "actor": actor,
                "runtime_invocation_id": invocation["runtime_invocation_id"],
                "status": "failed",
                "error_summary": error_message,
                "summary": "DeerFlow lead agent run failed.",
            },
        )
        raise

    status = "succeeded" if completed else "lost"
    await _call_mcp_tool(
        "aicos_runtime_invocation_update",
        {
            "operating_scope_key": body.operating_scope_key,
            "idempotency_key": f"deerflow:runtime-terminal:{record.run_id}",
            "actor": actor,
            "runtime_invocation_id": invocation["runtime_invocation_id"],
            "status": status,
            "terminal_summary": "DeerFlow lead agent run completed." if completed else "DeerFlow run ended without a final checkpoint.",
            "summary": f"DeerFlow runtime {status}.",
        },
    )

    final_message = _last_assistant_message(final_state)
    return {
        "ok": True,
        "operating_scope_key": body.operating_scope_key,
        "route": "deerflow_lead_agent",
        "work_unit_ref": work_ref,
        "created_work_unit_ref": created_work.get("work_unit_ref") if created_work else None,
        "context_packet_ref": packet["context_packet_ref"],
        "runtime_invocation_ref": invocation["runtime_invocation_ref"],
        "thread_id": thread_id,
        "runId": record.run_id,
        "agentId": agent_name or "lead_agent",
        "status": status,
        "message": final_message or ("Run completed." if completed else "Run did not produce a final checkpoint."),
        "final_state": final_state,
        "error": error_message,
    }

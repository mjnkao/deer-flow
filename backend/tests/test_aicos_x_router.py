from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import aicos_x


def _client(monkeypatch, calls: list[tuple[str, dict]]):
    async def fake_call_mcp_tool(name: str, arguments: dict, *, timeout: float = 45):
        calls.append((name, arguments))
        if name == "aicos_status_projection":
            return {"ok": True, "sourceMode": "native", "workUnits": []}
        if name == "aicos_work_unit_create":
            return {"ok": True, "work_unit_id": "wu-1", "work_unit_ref": "WU-000001"}
        if name == "aicos_context_control_packet_build":
            return {"ok": True, "context_packet_id": "ctx-1", "context_packet_ref": "CTX-000001"}
        raise AssertionError(f"unexpected tool {name}")

    monkeypatch.setattr(aicos_x, "_call_mcp_tool", fake_call_mcp_tool)
    app = FastAPI()
    app.include_router(aicos_x.router)
    return TestClient(app)


def test_projection_reads_native_aicos_x(monkeypatch):
    calls: list[tuple[str, dict]] = []
    response = _client(monkeypatch, calls).get("/api/aicos-x/projection")

    assert response.status_code == 200
    assert response.json()["sourceMode"] == "native"
    assert calls == [("aicos_status_projection", {"operating_scope_key": "aicos-x"})]


def test_start_work_creates_work_unit_and_builds_context_packet(monkeypatch):
    calls: list[tuple[str, dict]] = []
    response = _client(monkeypatch, calls).post(
        "/api/aicos-x/start-work",
        json={
            "title": "Run dashboard integration test",
            "objective": "Verify the adapter path.",
            "assigned_agent_ref": "codex-coder",
            "upload_thread_id": "thread-upload-1",
            "uploaded_files": [
                {
                    "filename": "context.md",
                    "size": 12,
                    "virtual_path": "/uploads/context.md",
                    "artifact_url": "/api/artifacts/context.md",
                }
            ],
            "metadata": {
                "planning_placement": {
                    "direction_ref": "S-aicos-x",
                    "direction": "AI-human co-working",
                    "objective_ref": "O-agent-native-workspace",
                    "objective": "Agent-native workspace",
                }
            },
            "acceptance_criteria": ["A Work Unit exists", "A Context Packet exists"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["work_unit_ref"] == "WU-000001"
    assert [name for name, _ in calls] == ["aicos_work_unit_create", "aicos_context_control_packet_build"]
    assert calls[0][1]["criteria"][0]["criterion_key"] == "AC-1"
    assert calls[0][1]["status"] == "captured"
    assert calls[0][1]["metadata"]["assigned_agent_ref"] == "codex-coder"
    assert calls[0][1]["metadata"]["planning_placement"]["objective_ref"] == "O-agent-native-workspace"
    assert calls[1][1]["context_profile_key"] == "deerflow.lead_agent.execution.v1"
    assert calls[1][1]["agent_ref"] == "codex-coder"
    assert calls[1][1]["metadata"]["assigned_agent_ref"] == "codex-coder"
    assert calls[1][1]["metadata"]["planning_placement"]["direction_ref"] == "S-aicos-x"
    assert calls[1][1]["source_refs"][1]["kind"] == "upload"


def test_start_work_rejects_unregistered_owner_ref(monkeypatch):
    calls: list[tuple[str, dict]] = []
    response = _client(monkeypatch, calls).post(
        "/api/aicos-x/start-work",
        json={
            "title": "Bad owner",
            "objective": "Owner must not come from a legacy chat persona.",
            "owner_ref": "xu",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "aicos_x_owner_ref_not_allowed"
    assert calls == []


def test_generic_mcp_blocks_native_write_tool(monkeypatch):
    calls: list[tuple[str, dict]] = []
    response = _client(monkeypatch, calls).post(
        "/api/aicos-x/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "aicos_work_unit_create", "arguments": {}},
        },
    )

    assert response.status_code == 423
    assert response.json()["detail"]["code"] == "aicos_x_write_blocked"
    assert calls == []

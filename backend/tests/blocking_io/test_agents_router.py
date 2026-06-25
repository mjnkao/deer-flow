"""Regression anchors: the custom-agent router must not block the event loop.

``app.gateway.routers.agents.create_agent_endpoint`` and ``delete_agent`` are
async route handlers that resolve the agent directory (``Paths.base_dir`` calls
``Path.resolve``), probe it (``Path.exists``), and create/remove it (``mkdir``,
config/SOUL writes, ``shutil.rmtree``) — all blocking IO. Both offload that work
via ``asyncio.to_thread``; if any of it regresses back onto the event loop, the
strict Blockbuster gate raises ``BlockingError`` and these tests fail.

Imports live at module scope so the one-time FastAPI app construction (which
reads files while building OpenAPI schemas) happens at collection time, not on
the event loop under test. Test-side path resolution is itself offloaded with
``asyncio.to_thread`` (matching ``test_uploads_middleware``) so only the
handlers' own filesystem access is exercised on the loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.gateway.routers.agents import (
    AgentCreateRequest,
    AgentProfileFileUpdateRequest,
    create_agent_endpoint,
    delete_agent,
    get_agent_profile_file,
    list_agent_profile_files,
    update_agent_profile_file,
)
from deerflow.config.agents_api_config import load_agents_api_config_from_dict
from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import get_effective_user_id

pytestmark = pytest.mark.asyncio


async def test_create_agent_does_not_block_event_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    load_agents_api_config_from_dict({"enabled": True})
    try:
        response = await create_agent_endpoint(AgentCreateRequest(name="loop-make-agent", soul="You are a test agent."))
        assert response is not None

        user_id = get_effective_user_id()
        # test-side check (resolution offloaded; not exercised on the loop)
        agent_dir = await asyncio.to_thread(get_paths().user_agent_dir, user_id, "loop-make-agent")
        assert await asyncio.to_thread((agent_dir / "config.yaml").exists)
    finally:
        load_agents_api_config_from_dict({})


async def test_delete_agent_does_not_block_event_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    load_agents_api_config_from_dict({"enabled": True})
    try:
        user_id = get_effective_user_id()
        user_id = get_effective_user_id()
        # test-side seeding (resolution offloaded; not exercised on the loop)
        agent_dir = await asyncio.to_thread(get_paths().user_agent_dir, user_id, "loop-test-agent")
        await asyncio.to_thread(agent_dir.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread((agent_dir / "config.yaml").write_text, "name: loop-test-agent\n", encoding="utf-8")

        await delete_agent("loop-test-agent")

        assert not await asyncio.to_thread(agent_dir.exists)
    finally:
        load_agents_api_config_from_dict({})


async def test_agent_profile_files_read_and_update_allowlisted_files(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    runtime_home = tmp_path / "runtime"
    project_root.mkdir()
    runtime_home.mkdir()
    (project_root / "config.yaml").write_text("agents_api:\n  enabled: true\nmodels: []\n", encoding="utf-8")
    (project_root / "extensions_config.json").write_text('{"mcpServers": {}, "skills": {}}\n', encoding="utf-8")
    (project_root / "AGENTS.md").write_text("# Project agents\n", encoding="utf-8")

    monkeypatch.setenv("DEER_FLOW_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("DEER_FLOW_HOME", str(runtime_home))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    load_agents_api_config_from_dict({"enabled": True})
    try:
        await create_agent_endpoint(AgentCreateRequest(name="profile-test", soul="old soul"))

        listing = await list_agent_profile_files()
        ids = {item.id for item in listing.files}
        assert {"app.config", "app.extensions", "repo.agents", "runtime.user", "agent.profile-test.soul", "agent.profile-test.config"} <= ids

        soul = await get_agent_profile_file("agent.profile-test.soul")
        assert soul.content == "old soul"

        updated = await update_agent_profile_file("agent.profile-test.soul", AgentProfileFileUpdateRequest(content="new soul"))
        assert updated.content == "new soul"
        assert (runtime_home / "users" / get_effective_user_id() / "agents" / "profile-test" / "SOUL.md").read_text(encoding="utf-8") == "new soul"

        user_profile = await update_agent_profile_file("runtime.user", AgentProfileFileUpdateRequest(content="# User\n"))
        assert user_profile.exists is True
        assert (runtime_home / "USER.md").read_text(encoding="utf-8") == "# User\n"
    finally:
        load_agents_api_config_from_dict({})


async def test_agent_profile_files_reject_invalid_json(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "config.yaml").write_text("agents_api:\n  enabled: true\nmodels: []\n", encoding="utf-8")
    (project_root / "extensions_config.json").write_text('{"mcpServers": {}, "skills": {}}\n', encoding="utf-8")

    monkeypatch.setenv("DEER_FLOW_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("DEER_FLOW_HOME", str(tmp_path / "runtime"))
    monkeypatch.setattr("deerflow.config.paths._paths", None)
    load_agents_api_config_from_dict({"enabled": True})
    try:
        with pytest.raises(Exception) as exc:
            await update_agent_profile_file("app.extensions", AgentProfileFileUpdateRequest(content="{broken"))
        assert "Invalid JSON" in str(exc.value)
        assert (project_root / "extensions_config.json").read_text(encoding="utf-8") == '{"mcpServers": {}, "skills": {}}\n'
    finally:
        load_agents_api_config_from_dict({})

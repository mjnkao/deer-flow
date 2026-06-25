"""CRUD API for custom agents."""

import asyncio
import json
import logging
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deerflow.config.agents_api_config import get_agents_api_config
from deerflow.config.agents_config import AgentConfig, list_custom_agents, load_agent_config, load_agent_soul
from deerflow.config.app_config import AppConfig
from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.config.paths import get_paths
from deerflow.config.runtime_paths import project_root
from deerflow.runtime.user_context import get_effective_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")
MAX_PROFILE_FILE_BYTES = 1_000_000
PROFILE_FILE_LANGUAGES = {"markdown", "yaml", "json"}


@dataclass(frozen=True)
class AgentProfileFileDescriptor:
    id: str
    label: str
    path: Path
    kind: str
    language: Literal["markdown", "yaml", "json"]
    scope: str
    editable: bool = True


class AgentResponse(BaseModel):
    """Response model for a custom agent."""

    name: str = Field(..., description="Agent name (hyphen-case)")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    skills: list[str] | None = Field(default=None, description="Optional skill whitelist (None=all, []=none)")
    soul: str | None = Field(default=None, description="SOUL.md content")


class AgentsListResponse(BaseModel):
    """Response model for listing all custom agents."""

    agents: list[AgentResponse]


class AgentProfileFileSummary(BaseModel):
    """Safe, allowlisted profile/config file shown in the profile editor."""

    id: str
    label: str
    path: str
    kind: str
    language: Literal["markdown", "yaml", "json"]
    scope: str
    editable: bool
    exists: bool
    size: int | None = None
    updated_at: float | None = None


class AgentProfileFilesResponse(BaseModel):
    files: list[AgentProfileFileSummary]


class AgentProfileFileResponse(AgentProfileFileSummary):
    content: str = ""


class AgentProfileFileUpdateRequest(BaseModel):
    content: str = Field(default="", description="Full replacement file content.")


class AgentCreateRequest(BaseModel):
    """Request body for creating a custom agent."""

    name: str = Field(..., description="Agent name (must match ^[A-Za-z0-9-]+$, stored as lowercase)")
    description: str = Field(default="", description="Agent description")
    model: str | None = Field(default=None, description="Optional model override")
    tool_groups: list[str] | None = Field(default=None, description="Optional tool group whitelist")
    skills: list[str] | None = Field(default=None, description="Optional skill whitelist (None=all enabled, []=none)")
    soul: str = Field(default="", description="SOUL.md content — agent personality and behavioral guardrails")


class AgentUpdateRequest(BaseModel):
    """Request body for updating a custom agent."""

    description: str | None = Field(default=None, description="Updated description")
    model: str | None = Field(default=None, description="Updated model override")
    tool_groups: list[str] | None = Field(default=None, description="Updated tool group whitelist")
    skills: list[str] | None = Field(default=None, description="Updated skill whitelist (None=all, []=none)")
    soul: str | None = Field(default=None, description="Updated SOUL.md content")


def _validate_agent_name(name: str) -> None:
    """Validate agent name against allowed pattern.

    Args:
        name: The agent name to validate.

    Raises:
        HTTPException: 422 if the name is invalid.
    """
    if not AGENT_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid agent name '{name}'. Must match ^[A-Za-z0-9-]+$ (letters, digits, and hyphens only).",
        )


def _normalize_agent_name(name: str) -> str:
    """Normalize agent name to lowercase for filesystem storage."""
    return name.lower()


def _require_agents_api_enabled() -> None:
    """Reject access unless the custom-agent management API is explicitly enabled."""
    if not get_agents_api_config().enabled:
        raise HTTPException(
            status_code=403,
            detail=("Custom-agent management API is disabled. Set agents_api.enabled=true to expose agent and user-profile routes over HTTP."),
        )


def _file_language(path: Path) -> Literal["markdown", "yaml", "json"]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return "markdown"


def _profile_file_summary(desc: AgentProfileFileDescriptor) -> AgentProfileFileSummary:
    exists = desc.path.exists()
    stat = desc.path.stat() if exists else None
    return AgentProfileFileSummary(
        id=desc.id,
        label=desc.label,
        path=str(desc.path),
        kind=desc.kind,
        language=desc.language,
        scope=desc.scope,
        editable=desc.editable,
        exists=exists,
        size=stat.st_size if stat else None,
        updated_at=stat.st_mtime if stat else None,
    )


def _agent_profile_descriptors() -> dict[str, AgentProfileFileDescriptor]:
    """Return the explicit profile/config allowlist for the current user."""
    descriptors: dict[str, AgentProfileFileDescriptor] = {}
    root = project_root()

    def add(desc: AgentProfileFileDescriptor) -> None:
        descriptors[desc.id] = desc

    try:
        config_path = AppConfig.resolve_config_path()
        add(
            AgentProfileFileDescriptor(
                id="app.config",
                label="config.yaml",
                path=config_path,
                kind="app_config",
                language="yaml",
                scope="global",
            )
        )
    except FileNotFoundError:
        pass

    extensions_path = ExtensionsConfig.resolve_config_path()
    if extensions_path is not None:
        add(
            AgentProfileFileDescriptor(
                id="app.extensions",
                label=extensions_path.name,
                path=extensions_path,
                kind="extensions_config",
                language="json",
                scope="global",
            )
        )

    for file_id, label, path in (
        ("repo.agents", "AGENTS.md", root / "AGENTS.md"),
        ("backend.agents", "backend/AGENTS.md", root / "backend" / "AGENTS.md"),
        ("frontend.agents", "frontend/AGENTS.md", root / "frontend" / "AGENTS.md"),
    ):
        if path.exists():
            add(
                AgentProfileFileDescriptor(
                    id=file_id,
                    label=label,
                    path=path,
                    kind="instruction_doc",
                    language="markdown",
                    scope="repo",
                )
            )

    paths = get_paths()
    add(
        AgentProfileFileDescriptor(
            id="runtime.user",
            label="USER.md",
            path=paths.user_md_file,
            kind="user_profile",
            language="markdown",
            scope="runtime",
        )
    )

    user_id = get_effective_user_id()
    for agent in list_custom_agents(user_id=user_id):
        agent_dir = paths.user_agent_dir(user_id, agent.name)
        if not agent_dir.exists() and paths.agent_dir(agent.name).exists():
            agent_dir = paths.agent_dir(agent.name)
        for key, filename in (("soul", "SOUL.md"), ("config", "config.yaml"), ("memory", "memory.json")):
            path = agent_dir / filename
            if key == "memory" and not path.exists():
                continue
            add(
                AgentProfileFileDescriptor(
                    id=f"agent.{agent.name}.{key}",
                    label=f"{agent.name}/{filename}",
                    path=path,
                    kind=f"agent_{key}",
                    language=_file_language(path),
                    scope=f"agent:{agent.name}",
                    editable=agent_dir == paths.user_agent_dir(user_id, agent.name),
                )
            )

    return descriptors


def _require_profile_file(file_id: str) -> AgentProfileFileDescriptor:
    desc = _agent_profile_descriptors().get(file_id)
    if desc is None:
        raise HTTPException(status_code=404, detail=f"Profile file '{file_id}' is not available in the DeerFlow profile allowlist.")
    return desc


def _validate_profile_content(desc: AgentProfileFileDescriptor, content: str) -> None:
    byte_len = len(content.encode("utf-8"))
    if byte_len > MAX_PROFILE_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"Profile file is too large ({byte_len} bytes, max {MAX_PROFILE_FILE_BYTES}).")
    if desc.language == "json":
        try:
            json.loads(content or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}") from exc
    if desc.language == "yaml" and content.strip():
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            logger.warning("Failed to remove temporary profile file %s", tmp_path)


def _agent_config_to_response(agent_cfg: AgentConfig, include_soul: bool = False, *, user_id: str | None = None) -> AgentResponse:
    """Convert AgentConfig to AgentResponse."""
    soul: str | None = None
    if include_soul:
        soul = load_agent_soul(agent_cfg.name, user_id=user_id) or ""

    return AgentResponse(
        name=agent_cfg.name,
        description=agent_cfg.description,
        model=agent_cfg.model,
        tool_groups=agent_cfg.tool_groups,
        skills=agent_cfg.skills,
        soul=soul,
    )


@router.get(
    "/agents",
    response_model=AgentsListResponse,
    summary="List Custom Agents",
    description="List all custom agents available in the agents directory, including their soul content.",
)
async def list_agents() -> AgentsListResponse:
    """List all custom agents.

    Returns:
        List of all custom agents with their metadata and soul content.
    """
    _require_agents_api_enabled()

    user_id = get_effective_user_id()
    try:
        agents = list_custom_agents(user_id=user_id)
        return AgentsListResponse(agents=[_agent_config_to_response(a, include_soul=True, user_id=user_id) for a in agents])
    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.get(
    "/agents/check",
    summary="Check Agent Name",
    description="Validate an agent name and check if it is available (case-insensitive).",
)
async def check_agent_name(name: str) -> dict:
    """Check whether an agent name is valid and not yet taken.

    Args:
        name: The agent name to check.

    Returns:
        ``{"available": true/false, "name": "<normalized>"}``

    Raises:
        HTTPException: 422 if the name is invalid.
    """
    _require_agents_api_enabled()
    _validate_agent_name(name)
    normalized = _normalize_agent_name(name)
    user_id = get_effective_user_id()
    paths = get_paths()
    # Treat the name as taken if either the per-user path or the legacy shared
    # path holds an agent — picking a name that collides with an unmigrated
    # legacy agent would shadow the legacy entry once migration runs.
    available = not paths.user_agent_dir(user_id, normalized).exists() and not paths.agent_dir(normalized).exists()
    return {"available": available, "name": normalized}


@router.get(
    "/agents/{name}",
    response_model=AgentResponse,
    summary="Get Custom Agent",
    description="Retrieve details and SOUL.md content for a specific custom agent.",
)
async def get_agent(name: str) -> AgentResponse:
    """Get a specific custom agent by name.

    Args:
        name: The agent name.

    Returns:
        Agent details including SOUL.md content.

    Raises:
        HTTPException: 404 if agent not found.
    """
    _require_agents_api_enabled()
    _validate_agent_name(name)
    name = _normalize_agent_name(name)
    user_id = get_effective_user_id()

    try:
        agent_cfg = load_agent_config(name, user_id=user_id)
        return _agent_config_to_response(agent_cfg, include_soul=True, user_id=user_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    except Exception as e:
        logger.error(f"Failed to get agent '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")


@router.post(
    "/agents",
    response_model=AgentResponse,
    status_code=201,
    summary="Create Custom Agent",
    description="Create a new custom agent with its config and SOUL.md.",
)
async def create_agent_endpoint(request: AgentCreateRequest) -> AgentResponse:
    """Create a new custom agent.

    Args:
        request: The agent creation request.

    Returns:
        The created agent details.

    Raises:
        HTTPException: 409 if agent already exists, 422 if name is invalid.
    """
    _require_agents_api_enabled()
    _validate_agent_name(request.name)
    normalized_name = _normalize_agent_name(request.name)
    user_id = get_effective_user_id()
    paths = get_paths()

    def _create_agent() -> AgentResponse | None:
        # Worker thread: base-dir resolution, existence checks, directory/file
        # creation, read-back, and failure cleanup are all blocking filesystem
        # IO that must stay off the event loop.
        agent_dir = paths.user_agent_dir(user_id, normalized_name)
        legacy_dir = paths.agent_dir(normalized_name)

        if legacy_dir.exists():
            return None  # signals 409 to the caller

        try:
            try:
                agent_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                return None  # signals 409 to the caller
            # Write config.yaml
            config_data: dict = {"name": normalized_name}
            if request.description:
                config_data["description"] = request.description
            if request.model is not None:
                config_data["model"] = request.model
            if request.tool_groups is not None:
                config_data["tool_groups"] = request.tool_groups
            if request.skills is not None:
                config_data["skills"] = request.skills

            config_file = agent_dir / "config.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

            # Write SOUL.md
            soul_file = agent_dir / "SOUL.md"
            soul_file.write_text(request.soul, encoding="utf-8")

            logger.info(f"Created agent '{normalized_name}' at {agent_dir}")

            agent_cfg = load_agent_config(normalized_name, user_id=user_id)
            return _agent_config_to_response(agent_cfg, include_soul=True, user_id=user_id)
        except Exception:
            # Clean up partial state on failure before surfacing the error.
            if agent_dir.exists():
                shutil.rmtree(agent_dir)
            raise

    try:
        response = await asyncio.to_thread(_create_agent)
    except Exception as e:
        logger.error(f"Failed to create agent '{request.name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")

    if response is None:
        raise HTTPException(status_code=409, detail=f"Agent '{normalized_name}' already exists")

    return response


@router.put(
    "/agents/{name}",
    response_model=AgentResponse,
    summary="Update Custom Agent",
    description="Update an existing custom agent's config and/or SOUL.md.",
)
async def update_agent(name: str, request: AgentUpdateRequest) -> AgentResponse:
    """Update an existing custom agent.

    Args:
        name: The agent name.
        request: The update request (all fields optional).

    Returns:
        The updated agent details.

    Raises:
        HTTPException: 404 if agent not found.
    """
    _require_agents_api_enabled()
    _validate_agent_name(name)
    name = _normalize_agent_name(name)
    user_id = get_effective_user_id()

    try:
        agent_cfg = load_agent_config(name, user_id=user_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    paths = get_paths()
    agent_dir = paths.user_agent_dir(user_id, name)
    if not agent_dir.exists() and paths.agent_dir(name).exists():
        raise HTTPException(
            status_code=409,
            detail=(f"Agent '{name}' only exists in the legacy shared layout and is not scoped to a user. Run scripts/migrate_user_isolation.py to move legacy agents into the per-user layout before updating."),
        )

    try:
        # Update config if any config fields changed
        # Use model_fields_set to distinguish "field omitted" from "explicitly set to null".
        # This is critical for skills where None means "inherit all" (not "don't change").
        fields_set = request.model_fields_set
        config_changed = bool(fields_set & {"description", "model", "tool_groups", "skills"})

        if config_changed:
            updated: dict = {
                "name": agent_cfg.name,
                "description": request.description if "description" in fields_set else agent_cfg.description,
            }
            new_model = request.model if "model" in fields_set else agent_cfg.model
            if new_model is not None:
                updated["model"] = new_model

            new_tool_groups = request.tool_groups if "tool_groups" in fields_set else agent_cfg.tool_groups
            if new_tool_groups is not None:
                updated["tool_groups"] = new_tool_groups

            # skills: None = inherit all, [] = no skills, ["a","b"] = whitelist
            if "skills" in fields_set:
                new_skills = request.skills
            else:
                new_skills = agent_cfg.skills
            if new_skills is not None:
                updated["skills"] = new_skills

            config_file = agent_dir / "config.yaml"
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(updated, f, default_flow_style=False, allow_unicode=True)

        # Update SOUL.md if provided
        if request.soul is not None:
            soul_path = agent_dir / "SOUL.md"
            soul_path.write_text(request.soul, encoding="utf-8")

        logger.info(f"Updated agent '{name}'")

        refreshed_cfg = load_agent_config(name, user_id=user_id)
        return _agent_config_to_response(refreshed_cfg, include_soul=True, user_id=user_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


class UserProfileResponse(BaseModel):
    """Response model for the global user profile (USER.md)."""

    content: str | None = Field(default=None, description="USER.md content, or null if not yet created")


class UserProfileUpdateRequest(BaseModel):
    """Request body for setting the global user profile."""

    content: str = Field(default="", description="USER.md content — describes the user's background and preferences")


@router.get(
    "/user-profile",
    response_model=UserProfileResponse,
    summary="Get User Profile",
    description="Read the global USER.md file that is injected into all custom agents.",
)
async def get_user_profile() -> UserProfileResponse:
    """Return the current USER.md content.

    Returns:
        UserProfileResponse with content=None if USER.md does not exist yet.
    """
    _require_agents_api_enabled()

    try:
        user_md_path = get_paths().user_md_file
        if not user_md_path.exists():
            return UserProfileResponse(content=None)
        raw = user_md_path.read_text(encoding="utf-8").strip()
        return UserProfileResponse(content=raw or None)
    except Exception as e:
        logger.error(f"Failed to read user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read user profile: {str(e)}")


@router.put(
    "/user-profile",
    response_model=UserProfileResponse,
    summary="Update User Profile",
    description="Write the global USER.md file that is injected into all custom agents.",
)
async def update_user_profile(request: UserProfileUpdateRequest) -> UserProfileResponse:
    """Create or overwrite the global USER.md.

    Args:
        request: The update request with the new USER.md content.

    Returns:
        UserProfileResponse with the saved content.
    """
    _require_agents_api_enabled()

    try:
        paths = get_paths()
        paths.base_dir.mkdir(parents=True, exist_ok=True)
        paths.user_md_file.write_text(request.content, encoding="utf-8")
        logger.info(f"Updated USER.md at {paths.user_md_file}")
        return UserProfileResponse(content=request.content or None)
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update user profile: {str(e)}")


@router.get(
    "/agent-profile-files",
    response_model=AgentProfileFilesResponse,
    summary="List Agent Profile Files",
    description="List allowlisted DeerFlow agent profile and configuration files that can be edited from the workspace UI.",
)
async def list_agent_profile_files() -> AgentProfileFilesResponse:
    """List safe profile/config files for the current runtime/user boundary."""
    _require_agents_api_enabled()

    try:
        files = await asyncio.to_thread(lambda: [_profile_file_summary(desc) for desc in _agent_profile_descriptors().values()])
        files.sort(key=lambda item: (item.scope, item.label))
        return AgentProfileFilesResponse(files=files)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list agent profile files: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list profile files: {str(e)}")


@router.get(
    "/agent-profile-files/{file_id}",
    response_model=AgentProfileFileResponse,
    summary="Get Agent Profile File",
    description="Read an allowlisted DeerFlow agent profile or configuration file.",
)
async def get_agent_profile_file(file_id: str) -> AgentProfileFileResponse:
    """Read one allowlisted profile/config file by id."""
    _require_agents_api_enabled()

    def _read() -> AgentProfileFileResponse:
        desc = _require_profile_file(file_id)
        summary = _profile_file_summary(desc)
        if not desc.path.exists():
            return AgentProfileFileResponse(**summary.model_dump(), content="")
        if desc.path.stat().st_size > MAX_PROFILE_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"Profile file '{file_id}' exceeds the {MAX_PROFILE_FILE_BYTES} byte editor limit.")
        return AgentProfileFileResponse(**summary.model_dump(), content=desc.path.read_text(encoding="utf-8"))

    try:
        return await asyncio.to_thread(_read)
    except HTTPException:
        raise
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=415, detail=f"Profile file '{file_id}' is not valid UTF-8 text.") from e
    except Exception as e:
        logger.error("Failed to read agent profile file %s: %s", file_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read profile file: {str(e)}")


@router.put(
    "/agent-profile-files/{file_id}",
    response_model=AgentProfileFileResponse,
    summary="Update Agent Profile File",
    description="Atomically write an allowlisted DeerFlow agent profile or configuration file.",
)
async def update_agent_profile_file(file_id: str, request: AgentProfileFileUpdateRequest) -> AgentProfileFileResponse:
    """Write one allowlisted profile/config file by id."""
    _require_agents_api_enabled()

    def _write() -> AgentProfileFileResponse:
        desc = _require_profile_file(file_id)
        if not desc.editable:
            raise HTTPException(status_code=409, detail=f"Profile file '{file_id}' is read-only in the legacy shared agent layout.")
        _validate_profile_content(desc, request.content)
        _atomic_write_text(desc.path, request.content)
        summary = _profile_file_summary(desc)
        return AgentProfileFileResponse(**summary.model_dump(), content=request.content)

    try:
        return await asyncio.to_thread(_write)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update agent profile file %s: %s", file_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update profile file: {str(e)}")


@router.delete(
    "/agents/{name}",
    status_code=204,
    summary="Delete Custom Agent",
    description="Delete a custom agent and all its files (config, SOUL.md, memory).",
)
async def delete_agent(name: str) -> None:
    """Delete a custom agent.

    Args:
        name: The agent name.

    Raises:
        HTTPException: 404 if no per-user copy exists; 409 if only a legacy
            shared copy exists (suggesting the migration script).
    """
    _require_agents_api_enabled()
    _validate_agent_name(name)
    name = _normalize_agent_name(name)
    user_id = get_effective_user_id()
    paths = get_paths()

    def _remove_agent_dir() -> tuple[str, str]:
        # Runs in a worker thread: resolving the base dir, probing the directory
        # (`exists`), and removing it (`rmtree`) are all blocking filesystem IO
        # that must stay off the event loop.
        agent_dir = paths.user_agent_dir(user_id, name)
        if not agent_dir.exists():
            outcome = "legacy" if paths.agent_dir(name).exists() else "missing"
            return outcome, str(agent_dir)
        shutil.rmtree(agent_dir)
        return "deleted", str(agent_dir)

    try:
        outcome, agent_dir = await asyncio.to_thread(_remove_agent_dir)
    except Exception as e:
        logger.error(f"Failed to delete agent '{name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")

    if outcome == "legacy":
        raise HTTPException(
            status_code=409,
            detail=(f"Agent '{name}' only exists in the legacy shared layout and is not scoped to a user. Run scripts/migrate_user_isolation.py to move legacy agents into the per-user layout before deleting."),
        )
    if outcome == "missing":
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    logger.info(f"Deleted agent '{name}' from {agent_dir}")

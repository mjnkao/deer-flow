"""Optional DeerFlow module configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class DurableWorkflowsConfig(BaseModel):
    """Durable workflow runtime envelope and observability switches."""

    enabled: bool = Field(default=True, description="Create durable workflow envelopes around run execution.")
    api_enabled: bool = Field(default=True, description="Expose durable workflow read APIs.")
    auto_envelope_for_runs: bool = Field(default=True, description="Automatically bind API-created runs to workflow envelopes.")


class WorkModuleConfig(BaseModel):
    """Generic work unit module switches."""

    enabled: bool = Field(default=True, description="Enable generic work unit storage and API support.")
    api_enabled: bool = Field(default=True, description="Expose generic work unit APIs.")


class WorkBoardConfig(BaseModel):
    """Built-in WorkBoard UI switches."""

    enabled: bool = Field(default=True, description="Expose the built-in WorkBoard UI surface.")


class ModulesConfig(BaseModel):
    """Feature gates for optional DeerFlow modules.

    The gates intentionally separate runtime primitives, generic work units,
    and the built-in WorkBoard UI. Integrations can enable the lower layers
    without accepting DeerFlow's default product surface.
    """

    durable_workflows: DurableWorkflowsConfig = Field(default_factory=DurableWorkflowsConfig)
    work: WorkModuleConfig = Field(default_factory=WorkModuleConfig)
    work_board: WorkBoardConfig = Field(default_factory=WorkBoardConfig)

    @model_validator(mode="after")
    def _apply_dependencies(self) -> "ModulesConfig":
        if self.work_board.enabled:
            self.work.enabled = True
            self.work.api_enabled = True
        if self.durable_workflows.enabled:
            self.durable_workflows.api_enabled = True
        return self

"""Optional DeerFlow module configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DurableWorkflowsConfig(BaseModel):
    """Durable workflow runtime envelope and observability switches."""

    enabled: bool = Field(default=True, description="Create durable workflow envelopes around run execution.")
    api_enabled: bool = Field(default=True, description="Expose durable workflow read APIs.")
    auto_envelope_for_runs: bool = Field(default=True, description="Automatically bind API-created runs to workflow envelopes.")


class WorkModuleConfig(BaseModel):
    """Generic work unit module switches."""

    enabled: bool = Field(default=True, description="Enable generic work unit storage and API support.")
    api_enabled: bool = Field(default=True, description="Expose generic work unit APIs.")
    global_tools_enabled: bool = Field(
        default=False,
        description=(
            "Expose the generic work_units tool to every agent. Runtime-bound "
            "work_unit tools can still be attached to a specific work unit when this is false."
        ),
    )


class ModulesConfig(BaseModel):
    """Feature gates for optional DeerFlow modules.

    The gates intentionally separate runtime primitives from generic work-unit
    records. UI surfaces and PM-tool adapters can extend this config later
    without being required by the durable runtime layer.
    """

    durable_workflows: DurableWorkflowsConfig = Field(default_factory=DurableWorkflowsConfig)
    work: WorkModuleConfig = Field(default_factory=WorkModuleConfig)

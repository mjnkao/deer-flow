"""Tests for module feature flag router."""

import pytest

from deerflow.config.app_config import AppConfig, reset_app_config, set_app_config


@pytest.mark.anyio
async def test_modules_router_includes_work_module_flags():
    from app.gateway.routers.modules import get_modules

    set_app_config(
        AppConfig.model_validate(
            {
                "sandbox": {"use": "deerflow.sandbox.local:LocalSandboxProvider"},
                "modules": {"work": {"enabled": True, "api_enabled": False}},
            }
        )
    )
    try:
        payload = await get_modules()
    finally:
        reset_app_config()

    assert payload["durable_workflows"]["enabled"] is True
    assert payload["work"] == {"enabled": True, "api_enabled": False}

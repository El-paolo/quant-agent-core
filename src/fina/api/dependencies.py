"""
Shared FastAPI dependency functions.

SettingsDep    — injects Settings into any route.
AgentSettingsDep — same, but validates agent keys are present first.
"""

from typing import Annotated

from fastapi import Depends

from fina.core.config import Settings, get_settings


def get_settings_dep() -> Settings:
    """FastAPI dependency: return application settings."""
    return get_settings()


def require_agent_settings(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Settings:
    """
    FastAPI dependency: return settings only if agent keys are configured.

    Raises:
        ConfigError: propagated as HTTP 503 by the agent route handler.
    """
    settings.validate_for_agent()
    return settings


# Annotated aliases for use in route signatures
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
AgentSettingsDep = Annotated[Settings, Depends(require_agent_settings)]

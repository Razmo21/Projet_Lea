"""Official OpenHands prompt extension without replacing its native agent prompt."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .model_registry import LoadedModelRegistry


def development_openhands_suffix(registry: LoadedModelRegistry) -> str:
    """Return the central contract plus Programming instructions for OpenHands.

    OpenHands owns its built-in agent prompt.  This suffix is intentionally
    separate so the SDK adapter can use `AgentContext.system_message_suffix`
    rather than the unsupported and destructive `system_prompt=` replacement.
    """

    return registry.system_prompt("development", include_memory=False)


def build_openhands_agent_context(
    registry: LoadedModelRegistry,
    agent_context_factory: Callable[..., Any],
) -> Any:
    """Instantiate the SDK's official context with no project/user skill loading.

    The factory is injected to keep the ordinary FastAPI environment independent
    from the SDK-only virtual environment.  The final OpenHands runner passes
    `openhands.sdk.AgentContext` as this factory.
    """

    return agent_context_factory(
        system_message_suffix=development_openhands_suffix(registry),
        load_user_skills=False,
        load_public_skills=False,
        load_project_skills=False,
        load_memory=False,
    )

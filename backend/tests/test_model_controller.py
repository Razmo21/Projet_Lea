from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.model_controller import ModelControllerError, PowerShellModelController  # noqa: E402
from app.model_registry import load_model_registry  # noqa: E402
from app.openhands_runtime import (  # noqa: E402
    AGENT_SERVER_MODE_IDLE,
    AgentServerHandle,
    DevelopmentReadiness,
    OpenHandsRuntimeError,
)


class FakeOpenHandsRuntime:
    """Records only controller requests; it never starts Docker in this unit suite."""

    def __init__(self, *, fail_docker: bool = False, ready: bool = True) -> None:
        """Configure an optional prerequisite failure and an observable readiness result."""

        self.fail_docker = fail_docker
        self.ready = ready
        self.calls: list[str] = []
        self.handle = AgentServerHandle("a" * 64, "idle", None, None, AGENT_SERVER_MODE_IDLE)

    async def require_docker(self) -> None:
        """Model the explicit Docker prerequisite without any automatic start."""

        self.calls.append("require_docker")
        if self.fail_docker:
            raise OpenHandsRuntimeError("Docker Desktop absent.")

    async def start_agent_server(self):
        """Return a deterministic idle container handle for the successful path."""

        self.calls.append("start_idle")
        return self.handle

    async def stop_agent_server(self, handle: AgentServerHandle) -> None:
        """Record only the exact handle supplied by the controller rollback."""

        self.calls.append(f"stop:{handle.container_id}")

    async def stop_idle_agent_server(self) -> None:
        """Record a General restore request without touching a real container."""

        self.calls.append("stop_idle")

    async def status(self) -> DevelopmentReadiness:
        """Expose a fully ready or deliberately incomplete Programming topology."""

        return DevelopmentReadiness(
            docker_available=True,
            agent_server_available=self.ready,
            qwen_available=True,
            profile_ready=self.ready,
            message="Le profil Programmation est prêt." if self.ready else "Agent absent.",
        )

    async def wait_until_ready(self) -> DevelopmentReadiness:
        """Model the bounded production readiness retry without a real delay."""

        self.calls.append("wait_ready")
        return await self.status()


class RecordingController(PowerShellModelController):
    """Replaces only child-process calls while exercising the production switch state machine."""

    def __init__(self, runtime: FakeOpenHandsRuntime, *, development_ready: bool = True) -> None:
        """Use the real registry but make process commands deterministic and in-memory."""

        super().__init__(registry=load_model_registry(), openhands_runtime=runtime)
        self.calls: list[str] = []
        self.development_ready = development_ready

    async def _general_script(self, action: str) -> None:
        """Record the fixed PowerShell action instead of launching a process in a unit test."""

        self.calls.append(f"general:{action}")

    async def _development_script(self, action: str) -> dict[str, object]:
        """Record the fixed Qwen lifecycle action and expose a configurable readiness state."""

        self.calls.append(f"development:{action}")
        return {"state": "ready" if action != "start" or self.development_ready else "error"}


class ModelControllerTests(unittest.IsolatedAsyncioTestCase):
    """Validate safe ordering and rollback without relying on a live model or Docker."""

    async def test_development_stops_general_then_requires_every_local_dependency(self) -> None:
        """A successful switch cannot publish Programming before Qwen and OpenHands readiness agree."""

        runtime = FakeOpenHandsRuntime()
        controller = RecordingController(runtime)
        self.assertEqual(await controller.activate("development"), "development")
        self.assertEqual(controller.calls, ["general:stop-model", "development:start"])
        self.assertEqual(runtime.calls, ["require_docker", "start_idle", "wait_ready"])

    async def test_development_failure_restores_general_after_owned_cleanup(self) -> None:
        """A missing Docker prerequisite leaves General restored rather than silently stopped."""

        runtime = FakeOpenHandsRuntime(fail_docker=True)
        controller = RecordingController(runtime)
        with self.assertRaisesRegex(ModelControllerError, "Docker Desktop"):
            await controller.activate("development")
        self.assertEqual(controller.calls, ["development:stop", "general:start-model"])
        self.assertEqual(runtime.calls, ["require_docker"])

    async def test_return_to_general_stops_programming_owners_before_general_start(self) -> None:
        """The return path does not leave an idle Agent Server or Qwen process active beside General."""

        runtime = FakeOpenHandsRuntime()
        controller = RecordingController(runtime)
        self.assertEqual(await controller.activate("general"), "general")
        self.assertEqual(runtime.calls, ["stop_idle"])
        self.assertEqual(controller.calls, ["development:stop", "general:start-model"])


if __name__ == "__main__":
    unittest.main()

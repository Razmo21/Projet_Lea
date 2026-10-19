from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.model_registry import load_model_registry  # noqa: E402
from app.openhands_runtime import (  # noqa: E402
    AGENT_LABEL,
    AGENT_GIT_OVERLAY_OPTIONS,
    AGENT_GIT_OVERLAY_PATH,
    AGENT_MODE_LABEL,
    AGENT_POLICY_WORKSPACE_ENV,
    AGENT_POLICY_WORKSPACE_PATH,
    AGENT_RUN_LABEL,
    AGENT_SERVER_ENTRYPOINT,
    AGENT_SERVER_MODE_IDLE,
    AGENT_SERVER_NETWORK_MODE,
    AGENT_SERVER_TOOL_MODULES,
    AGENT_SERVER_USER,
    AGENT_TERMINAL_POLICY_CONTAINER_PATH,
    AGENT_TERMINAL_POLICY_SHA256,
    AGENT_SERVER_UNAVAILABLE_MESSAGE,
    AgentServerHandle,
    DOCKER_REQUIRED_MESSAGE,
    MODEL_UNAVAILABLE_MESSAGE,
    OpenHandsRuntime,
    OpenHandsRuntimeError,
)


class OpenHandsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Exercise readiness truthfully without starting Docker or a model in unit tests."""

    def setUp(self) -> None:
        """Load the production registry so the checks cannot drift from its endpoints."""

        self.registry = load_model_registry()

    async def test_inspection_requires_confirmed_absence(self) -> None:
        """Daemon errors and malformed inspection never authorize a terminal state."""

        runtime = OpenHandsRuntime(self.registry)
        for responses in (
            [OpenHandsRuntimeError("offline"), OpenHandsRuntimeError("offline")],
            [OpenHandsRuntimeError("inspect failed"), "abc123"],
            ["[null]"],
        ):
            with patch.object(runtime, "_docker", new=AsyncMock(side_effect=responses)):
                with self.assertRaises(OpenHandsRuntimeError):
                    await runtime._inspect_container("lea-owned")
        with patch.object(runtime, "_docker", new=AsyncMock(side_effect=[OpenHandsRuntimeError("absent"), ""])) as docker:
            self.assertIsNone(await runtime._inspect_container("lea-owned"))
            self.assertIn("name=^/lea\\-owned$", docker.call_args.args)

    def transport(self, handler):
        """Create a mock loopback transport for the small public endpoint contract."""

        return httpx.MockTransport(handler)

    async def test_docker_observations_are_cached_but_mutations_require_a_fresh_probe(self) -> None:
        """Status polling shares a bounded cache; a later daemon failure blocks a run."""

        runtime = OpenHandsRuntime(self.registry)
        with patch.object(runtime, "_docker_probe", new=AsyncMock(side_effect=[True, False])) as docker:
            self.assertTrue(await runtime.docker_available())
            self.assertTrue(await runtime.docker_available())
            self.assertEqual(docker.await_count, 1)
            with self.assertRaises(OpenHandsRuntimeError):
                await runtime.require_docker()
            self.assertEqual(docker.await_count, 2)

    async def test_stopped_container_cleanup_never_targets_active_unknown_or_volumes(self) -> None:
        """Cleanup is exact, repeatable, non-forced and preserves persistent state."""

        runtime = OpenHandsRuntime(self.registry)
        handle = AgentServerHandle("a" * 64, "owned", "run", Path("project"), "run")
        for running, owned in ((True, True), (None, True), (False, False)):
            with patch.object(runtime, "_inspect_container", new=AsyncMock(return_value={"Id": handle.container_id, "State": {"Running": running}})), patch.object(runtime, "_verify_container", return_value=owned), patch.object(runtime, "_docker", new=AsyncMock()) as docker:
                with self.assertRaises(OpenHandsRuntimeError):
                    await runtime.remove_stopped_agent_server(handle)
                docker.assert_not_called()
        with patch.object(runtime, "_inspect_container", new=AsyncMock(side_effect=[{"Id": handle.container_id, "State": {"Running": False}}, None])), patch.object(runtime, "_verify_container", return_value=True), patch.object(runtime, "_docker", new=AsyncMock()) as docker:
            await runtime.remove_stopped_agent_server(handle)
            await runtime.remove_stopped_agent_server(handle)
            docker.assert_awaited_once_with("container", "rm", handle.container_id)
        with patch.object(runtime, "_inspect_container", new=AsyncMock(side_effect=OpenHandsRuntimeError("offline"))):
            with self.assertRaises(OpenHandsRuntimeError):
                await runtime.remove_stopped_agent_server(handle)

    async def test_stop_requires_final_state_confirmation(self) -> None:
        """A returned stop command is not enough if subsequent inspection is uncertain."""

        runtime = OpenHandsRuntime(self.registry)
        handle = AgentServerHandle("a" * 64, "owned", "run", Path("project"), "run")
        for final_state in (True, None, False):
            with patch.object(runtime, "_inspect_container", new=AsyncMock(side_effect=[{"Id": handle.container_id, "State": {"Running": True}}, {"Id": handle.container_id, "State": {"Running": final_state}}])), patch.object(runtime, "_verify_container", return_value=True), patch.object(runtime, "_docker", new=AsyncMock()):
                if final_state is False:
                    await runtime.stop_agent_server(handle)
                else:
                    with self.assertRaises(OpenHandsRuntimeError):
                        await runtime.stop_agent_server(handle)

    def expected_container_security(self) -> dict[str, object]:
        """Return the immutable image process identity required for container adoption."""

        server = self.registry.document.openhands.agent_server
        return {
            "User": AGENT_SERVER_USER,
            "Entrypoint": AGENT_SERVER_ENTRYPOINT,
            "Cmd": [
                "--host",
                "0.0.0.0",
                "--port",
                str(server.container_port),
                "--import-modules",
                AGENT_SERVER_TOOL_MODULES,
            ],
        }

    def expected_host_security(self) -> dict[str, object]:
        """Return the exact loopback publication and resource limits for one test container."""

        server = self.registry.document.openhands.agent_server
        runtime = self.registry.document.openhands.agent_runtime
        return {
            "PortBindings": {
                f"{server.container_port}/tcp": [
                    {"HostIp": server.host, "HostPort": str(server.port)}
                ]
            },
            "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
            "Memory": runtime.memory_mib * 1024 * 1024,
            "MemorySwap": runtime.memory_mib * 1024 * 1024,
            "NanoCpus": runtime.cpus * 1_000_000_000,
            "PidsLimit": runtime.pids_limit,
            "SecurityOpt": ["no-new-privileges:true"],
            "PidMode": "",
            "IpcMode": "private",
            "CapAdd": None,
            "Devices": [],
        }

    def expected_agent_environment(self) -> list[str]:
        """Return the fixed environment that keeps an Agent Server local and minimal."""

        return OpenHandsRuntime(self.registry)._agent_environment()

    async def test_docker_missing_uses_the_prescribed_message_without_http_calls(self) -> None:
        """No container or HTTP check is attempted when Docker Desktop is unavailable."""

        async def docker_missing() -> bool:
            """Model the fixed Docker version command returning no usable engine."""

            return False

        runtime = OpenHandsRuntime(self.registry, docker_probe=docker_missing)
        status = await runtime.status()
        self.assertFalse(status.profile_ready)
        self.assertEqual(status.message, DOCKER_REQUIRED_MESSAGE)
        with self.assertRaisesRegex(OpenHandsRuntimeError, "Docker Desktop"):
            await runtime.require_docker()

    async def test_each_loopback_dependency_is_reported_without_fallback(self) -> None:
        """Qwen and Agent Server are independently verified on their registry endpoints."""

        async def docker_ready() -> bool:
            """Model a manually started Docker Desktop engine."""

            return True

        expected_alias = self.registry.profile("development").runtime.alias

        def qwen_only(request: httpx.Request) -> httpx.Response:
            """Serve Qwen while making the Agent Server endpoint unavailable."""

            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": expected_alias}]})
            return httpx.Response(503)

        agent_missing = OpenHandsRuntime(
            self.registry, docker_probe=docker_ready, transport=self.transport(qwen_only)
        )
        self.assertEqual((await agent_missing.status()).message, AGENT_SERVER_UNAVAILABLE_MESSAGE)
        on_demand = await agent_missing.status(require_agent_server=False)
        self.assertTrue(on_demand.profile_ready)
        self.assertFalse(on_demand.agent_server_available)
        self.assertIn("au lancement", on_demand.message)

        def agent_only(request: httpx.Request) -> httpx.Response:
            """Serve exactly the registered Agent Server health and tools responses."""

            if request.url.path == "/v1/models":
                return httpx.Response(503)
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/api/tools/":
                return httpx.Response(200, json=[{"name": name} for name in ("terminal", "file_editor", "task_tracker")])
            return httpx.Response(404)

        qwen_missing = OpenHandsRuntime(
            self.registry, docker_probe=docker_ready, transport=self.transport(agent_only)
        )
        self.assertEqual((await qwen_missing.status()).message, MODEL_UNAVAILABLE_MESSAGE)

    async def test_complete_local_topology_requires_exact_tools_and_alias(self) -> None:
        """A healthy profile needs Qwen plus all three genuine Agent Server tools."""

        async def docker_ready() -> bool:
            """Model the user having already started Docker Desktop manually."""

            return True

        expected_alias = self.registry.profile("development").runtime.alias

        def complete(request: httpx.Request) -> httpx.Response:
            """Serve the minimal Qwen and Agent Server protocol used by the final code."""

            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": expected_alias}]})
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/api/tools/":
                return httpx.Response(200, json={"tools": [{"name": name} for name in ("terminal", "file_editor", "task_tracker")]})
            return httpx.Response(404)

        runtime = OpenHandsRuntime(
            self.registry, docker_probe=docker_ready, transport=self.transport(complete)
        )
        status = await runtime.status()
        self.assertTrue(status.profile_ready)
        self.assertEqual(status.public()["message"], "Le profil Programmation est prêt.")

    def test_docker_desktop_project_mount_must_match_the_exact_frozen_l_drive_path(self) -> None:
        """Docker's translated bind source cannot broaden a run beyond its frozen project."""

        project = Path(r"L:\IA_WORKSPACE\Example")
        self.assertTrue(OpenHandsRuntime._project_mount_matches(r"L:\IA_WORKSPACE\Example", project))
        self.assertTrue(
            OpenHandsRuntime._project_mount_matches(
                "/run/desktop/mnt/host/l/IA_WORKSPACE/Example", project
            )
        )
        self.assertFalse(
            OpenHandsRuntime._project_mount_matches(
                "/run/desktop/mnt/host/l/SteamLibrary/Example", project
            )
        )

    def test_idle_container_must_keep_agent_state_outside_the_project_workspace(self) -> None:
        """Reject a legacy `/workspace` workdir even when its labels and volume otherwise match."""

        runtime = OpenHandsRuntime(self.registry)
        agent = self.registry.document.openhands.agent_server
        state = self.registry.document.openhands.agent_runtime
        handle = AgentServerHandle(
            container_id="a" * 64,
            name="lea-openhands-development-idle",
            run_id=None,
            project_path=None,
            mode=AGENT_SERVER_MODE_IDLE,
        )
        inspection = {
            "Config": {
                **self.expected_container_security(),
                "Image": agent.image,
                "WorkingDir": state.state_volume_path,
                "Env": self.expected_agent_environment(),
                "Labels": {
                    AGENT_LABEL: "true",
                    AGENT_MODE_LABEL: AGENT_SERVER_MODE_IDLE,
                    AGENT_RUN_LABEL: "",
                },
            },
            "HostConfig": {
                **self.expected_host_security(),
                "Privileged": False,
                "NetworkMode": AGENT_SERVER_NETWORK_MODE,
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": state.state_volume,
                    "Destination": state.state_volume_path,
                }
            ],
        }
        self.assertTrue(runtime._verify_container(inspection, handle))
        inspection["Config"]["WorkingDir"] = "/workspace"  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["Config"]["WorkingDir"] = state.state_volume_path  # type: ignore[index]
        inspection["Config"]["User"] = "root"  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["Config"]["User"] = AGENT_SERVER_USER  # type: ignore[index]
        inspection["Config"]["Env"][4] = "LITELLM_LOCAL_MODEL_COST_MAP=False"  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["Config"]["Env"][4] = "LITELLM_LOCAL_MODEL_COST_MAP=True"  # type: ignore[index]
        inspection["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] = "127.0.0.1"  # type: ignore[index]
        inspection["HostConfig"]["RestartPolicy"]["Name"] = "always"  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["HostConfig"]["RestartPolicy"]["Name"] = "no"  # type: ignore[index]
        inspection["HostConfig"]["Memory"] = 0  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))

    def test_run_container_requires_a_tmpfs_overlay_for_internal_git_metadata(self) -> None:
        """Keep Git metadata and the verified terminal policy outside the user bind."""

        runtime = OpenHandsRuntime(self.registry)
        agent = self.registry.document.openhands.agent_server
        state = self.registry.document.openhands.agent_runtime
        project = Path(r"L:\IA_WORKSPACE\Example")
        policy_source = runtime._terminal_policy_source()
        handle = AgentServerHandle(
            container_id="b" * 64,
            name="lea-openhands-run-example",
            run_id="example",
            project_path=project,
            mode="run",
        )
        inspection = {
            "Config": {
                **self.expected_container_security(),
                "Image": agent.image,
                "WorkingDir": state.state_volume_path,
                "Env": [
                    *self.expected_agent_environment(),
                    f"LEA_OPENHANDS_TERMINAL_POLICY_SHA256={AGENT_TERMINAL_POLICY_SHA256}",
                    f"{AGENT_POLICY_WORKSPACE_ENV}={AGENT_POLICY_WORKSPACE_PATH}",
                ],
                "Labels": {
                    AGENT_LABEL: "true",
                    AGENT_MODE_LABEL: "run",
                    AGENT_RUN_LABEL: "example",
                },
            },
            "HostConfig": {
                **self.expected_host_security(),
                "Privileged": False,
                "NetworkMode": AGENT_SERVER_NETWORK_MODE,
                "Tmpfs": {AGENT_GIT_OVERLAY_PATH: AGENT_GIT_OVERLAY_OPTIONS},
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": state.state_volume,
                    "Destination": state.state_volume_path,
                },
                {
                    "Type": "bind",
                    "Source": str(project),
                    "Destination": "/workspace",
                },
                {
                    "Type": "bind",
                    "Source": str(policy_source),
                    "Destination": AGENT_TERMINAL_POLICY_CONTAINER_PATH,
                    "RW": False,
                },
            ],
        }
        self.assertTrue(runtime._verify_container(inspection, handle))
        inspection["Mounts"].append(  # type: ignore[index]
            {"Type": "bind", "Source": r"L:\outside", "Destination": "/outside"}
        )
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["Mounts"].pop()  # type: ignore[index]
        inspection["HostConfig"]["Tmpfs"] = {}  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))

    def test_run_container_rejects_a_missing_or_writable_terminal_policy_mount(self) -> None:
        """A run cannot adopt a policy mount unless it is exact and read-only."""

        runtime = OpenHandsRuntime(self.registry)
        agent = self.registry.document.openhands.agent_server
        state = self.registry.document.openhands.agent_runtime
        project = Path(r"L:\IA_WORKSPACE\Example")
        policy_source = runtime._terminal_policy_source()
        handle = AgentServerHandle("c" * 64, "lea-openhands-run-example", "example", project, "run")
        inspection = {
            "Config": {
                **self.expected_container_security(),
                "Image": agent.image,
                "WorkingDir": state.state_volume_path,
                "Env": [
                    *self.expected_agent_environment(),
                    f"LEA_OPENHANDS_TERMINAL_POLICY_SHA256={AGENT_TERMINAL_POLICY_SHA256}",
                    f"{AGENT_POLICY_WORKSPACE_ENV}={AGENT_POLICY_WORKSPACE_PATH}",
                ],
                "Labels": {
                    AGENT_LABEL: "true",
                    AGENT_MODE_LABEL: "run",
                    AGENT_RUN_LABEL: "example",
                },
            },
            "HostConfig": {
                **self.expected_host_security(),
                "Privileged": False,
                "NetworkMode": AGENT_SERVER_NETWORK_MODE,
                "Tmpfs": {AGENT_GIT_OVERLAY_PATH: AGENT_GIT_OVERLAY_OPTIONS},
            },
            "Mounts": [
                {"Type": "volume", "Name": state.state_volume, "Destination": state.state_volume_path},
                {"Type": "bind", "Source": str(project), "Destination": "/workspace"},
                {
                    "Type": "bind",
                    "Source": str(policy_source),
                    "Destination": AGENT_TERMINAL_POLICY_CONTAINER_PATH,
                    "RW": False,
                },
            ],
        }
        self.assertTrue(runtime._verify_container(inspection, handle))
        inspection["Config"]["Env"] = [  # type: ignore[index]
            *self.expected_agent_environment(),
            f"LEA_OPENHANDS_TERMINAL_POLICY_SHA256={AGENT_TERMINAL_POLICY_SHA256}"
        ]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["Config"]["Env"] = [  # type: ignore[index]
            *self.expected_agent_environment(),
            f"LEA_OPENHANDS_TERMINAL_POLICY_SHA256={AGENT_TERMINAL_POLICY_SHA256}",
            f"{AGENT_POLICY_WORKSPACE_ENV}={AGENT_POLICY_WORKSPACE_PATH}",
        ]
        inspection["Mounts"][2]["RW"] = True  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))
        inspection["Mounts"].pop()  # type: ignore[index]
        self.assertFalse(runtime._verify_container(inspection, handle))


if __name__ == "__main__":
    unittest.main()

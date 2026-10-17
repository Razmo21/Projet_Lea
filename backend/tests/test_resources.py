"""Resource readings and lifecycle without a GPU, Docker or any workload mutation."""

import asyncio
from dataclasses import replace
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.model_registry import load_model_registry
from app.main import create_app
from app.model_controller import ModelControllerError
from app.resources import ResourceAlerts, ResourceMonitor, gpu_memory, memory_values


class ResourceTests(unittest.IsolatedAsyncioTestCase):
    """Exercise persistent thresholds and a single, bounded, read-only loop."""

    def setUp(self) -> None:
        """Use the shipped profile policy, not test-specific production thresholds."""

        registry = load_model_registry()
        self.policy = registry.document.resource_policies[registry.profile("development").resource_policy]
        self.services = {"openhands_required": True, "docker_available": True, "model_available": True, "agent_server_available": None, "run_active": False}

    def test_non_agent_profile_does_not_require_docker(self) -> None:
        """General and future direct profiles keep resource alerts without Docker warnings."""

        alerts = ResourceAlerts(self.policy)
        ram = memory_values(32 * 1024**3, 12 * 1024**3)
        services = {**self.services, "openhands_required": False, "docker_available": None}
        self.assertEqual(alerts.evaluate(ram, 10, None, services, fresh_gpu=True), ("NORMAL", []))
        services["model_available"] = False
        level, messages = alerts.evaluate(ram, 10, None, services, fresh_gpu=True)
        self.assertEqual(level, "WARNING")
        self.assertTrue(any("modèle actif" in item for item in messages))
        self.assertFalse(any("Docker" in item or "Programmation" in item for item in messages))

    async def test_services_follow_profile_capabilities_not_names(self) -> None:
        """An additional configured direct profile probes its own adapter, never Docker."""

        registry = load_model_registry()
        future = registry.document.profiles[0].model_copy(update={"id": "another-local-profile"})
        registry = replace(registry, document=registry.document.model_copy(update={
            "profiles": [*registry.document.profiles, future],
        }))
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(Path(directory) / "test.sqlite3", model_gateway=object(), model_registry=registry)
            app.state.database.initialize()
            runtime = app.state.openhands_runtime
            adapter = SimpleNamespace(is_ready=AsyncMock(return_value=True))
            with patch("app.main.inference_adapter", return_value=adapter) as factory, patch.object(runtime, "docker_available", new=AsyncMock(return_value=False)) as docker, patch.object(runtime, "_agent_server_available", new=AsyncMock(return_value=False)) as agent:
                for profile_id in ("general", "another-local-profile", "development"):
                    with self.subTest(profile=profile_id):
                        app.state.runtime_coordinator.active_profile_id = profile_id
                        docker.reset_mock()
                        readings = await app.state.resource_monitor.services()
                        factory.assert_called_with(registry, profile_id)
                        self.assertTrue(readings["model_available"])
                        if profile_id == "development":
                            docker.assert_awaited_once()
                            self.assertFalse(readings["docker_available"])
                        else:
                            docker.assert_not_called()
                            self.assertIsNone(readings["docker_available"])
                        agent.assert_not_called()
                app.state.runtime_coordinator.active_agent_runs = 1
                await app.state.resource_monitor.services()
                agent.assert_awaited_once()

    async def test_profile_switch_preserves_system_cache_and_applies_policy(self) -> None:
        """Switch thresholds and alert ownership without duplicating GPU probes."""

        monitor = ResourceMonitor(self.policy, AsyncMock(return_value=self.services))
        monitor.set_active(True, profile_id="general")
        with patch("app.resources.gpu_memory", new=AsyncMock(return_value=None)) as gpu:
            await monitor.sample()
            next_policy = self.policy.model_copy(update={"system_available_warning_bytes": 10 * 1024**3})
            monitor.set_active(True, profile_id="another-local-profile", policy=next_policy)
            self.assertTrue(monitor.snapshot()["stale"])
            self.assertIs(monitor.alerts.policy, next_policy)
            self.assertEqual((await monitor.sample())["profile_id"], "another-local-profile")
            gpu.assert_awaited_once()
        await monitor.close()

    async def test_late_profile_sample_cannot_restore_previous_alerts(self) -> None:
        """Ignore an in-flight sample if the selected profile changes before it finishes."""

        monitor = ResourceMonitor(self.policy, AsyncMock(return_value=self.services))
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed_sample() -> dict:
            """Hold the old profile's snapshot until the switch has invalidated it."""

            entered.set()
            await release.wait()
            # End this one-shot test loop after the delayed publication check.
            monitor.closed = True
            return {"sampled_at": time.time(), "profile_id": "development"}

        with patch.object(monitor, "sample", side_effect=delayed_sample):
            monitor.set_active(True, profile_id="development")
            monitor.start()
            await entered.wait()
            monitor.set_active(True, profile_id="general")
            release.set()
            await monitor.task
            self.assertTrue(monitor.snapshot()["stale"])
        await monitor.close()

    def test_ram_validation_and_hysteresis(self) -> None:
        """Invalid readings stay unknown; recovery needs a margin and two measurements."""

        for total, free in ((0, 0), (10, -1), (10, 11), (float("nan"), 0), (10, float("inf"))):
            self.assertIsNone(memory_values(total, free))
        alerts = ResourceAlerts(self.policy)
        critical = memory_values(32 * 1024**3, self.policy.system_available_critical_bytes - 1)
        self.assertEqual(alerts.evaluate(critical, 10, None, self.services, fresh_gpu=True)[0], "NORMAL")
        self.assertEqual(alerts.evaluate(critical, 10, None, self.services, fresh_gpu=True)[0], "CRITICAL")
        border = memory_values(32 * 1024**3, self.policy.system_available_critical_bytes + 1)
        self.assertEqual(alerts.evaluate(border, 10, None, self.services, fresh_gpu=True)[0], "CRITICAL")
        healthy = memory_values(32 * 1024**3, 12 * 1024**3)
        alerts.evaluate(healthy, 10, None, self.services, fresh_gpu=True)
        self.assertEqual(alerts.evaluate(healthy, 10, None, self.services, fresh_gpu=True)[0], "NORMAL")

    def test_cpu_spike_is_not_persistent_pressure(self) -> None:
        """Require three high intervals and two low intervals, not an instantaneous peak."""

        alerts = ResourceAlerts(self.policy)
        ram = memory_values(32 * 1024**3, 12 * 1024**3)
        for cpu, expected in ((99, "NORMAL"), (20, "NORMAL"), (99, "NORMAL"), (99, "NORMAL"), (99, "WARNING"), (50, "WARNING"), (50, "NORMAL")):
            self.assertEqual(alerts.evaluate(ram, cpu, None, self.services, fresh_gpu=False)[0], expected)
        self.services.update(run_active=True, model_available=False)
        self.assertEqual(alerts.evaluate(ram, 20, None, self.services, fresh_gpu=False)[0], "CRITICAL")

    async def test_loop_is_unique_dormant_and_closed(self) -> None:
        """Repeated starts do not duplicate work and an inactive core leaves no periodic probes."""

        monitor = ResourceMonitor(self.policy, AsyncMock(return_value=self.services))
        monitor.interval = 0.01
        with patch.object(monitor, "sample", new=AsyncMock(return_value={"sampled_at": 1})) as sample:
            monitor.start()
            task = monitor.task
            monitor.start()
            self.assertIs(task, monitor.task)
            await asyncio.sleep(0.02)
            sample.assert_not_called()
            monitor.set_active(True)
            await asyncio.sleep(0.03)
            self.assertGreater(sample.call_count, 0)
            monitor.set_active(False)
            await asyncio.sleep(0.02)
            calls = sample.call_count
            await asyncio.sleep(0.03)
            self.assertEqual(sample.call_count, calls)
            await monitor.close()
            self.assertTrue(task.done())
            self.assertIsNone(monitor.task)

    def test_backend_start_switch_failure_and_shutdown_share_one_monitor(self) -> None:
        """The real lifespan enables General, follows switches and closes its only task."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            controller = SimpleNamespace(activate=AsyncMock(side_effect=["development", ModelControllerError("test failure"), "general"]))
            app = create_app(
                root / "test.sqlite3", model_controller=controller, workspace_root=workspace,
                checkpoint_root=root / "checkpoints", agent_runtime_root=root / "runs",
            )
            monitor = app.state.resource_monitor
            with patch.object(monitor, "sample", new=AsyncMock(return_value={"sampled_at": time.time()})):
                with TestClient(app) as client:
                    task = monitor.task
                    self.assertTrue(client.get("/api/resources").json()["active"])
                    self.assertEqual(monitor.profile_id, "general")
                    for profile_id, status, expected in (("development", 200, "development"), ("general", 503, "development"), ("general", 200, "general")):
                        self.assertEqual(client.post(f"/api/models/{profile_id}/activate").status_code, status)
                        self.assertEqual(monitor.profile_id, expected)
                        self.assertTrue(monitor.active)
                        self.assertIs(monitor.task, task)
                        registry = app.state.model_registry
                        self.assertEqual(monitor.policy, registry.document.resource_policies[registry.profile(expected).resource_policy])
                self.assertTrue(task.done())
                self.assertFalse(monitor.active)
                self.assertIsNone(monitor.task)

    def test_gpu_pressure_counts_only_new_measurements(self) -> None:
        """Cached GPU readings cannot turn one low sample into persistent pressure."""

        alerts = ResourceAlerts(self.policy)
        ram = memory_values(32 * 1024**3, 12 * 1024**3)
        gpu = memory_values(6 * 1024**3, 128 * 1024**2)
        for fresh, expected in ((True, "NORMAL"), (False, "NORMAL"), (False, "NORMAL"), (True, "WARNING")):
            self.assertEqual(alerts.evaluate(ram, 10, gpu, self.services, fresh_gpu=fresh)[0], expected)
        recovered = memory_values(6 * 1024**3, 2 * 1024**3)
        self.assertEqual(alerts.evaluate(ram, 10, recovered, self.services, fresh_gpu=True)[0], "NORMAL")

    async def test_gpu_invalid_outputs_are_unknown(self) -> None:
        """Malformed, multi-device and nonzero-exit NVIDIA responses stay unavailable."""

        for output, code in ((b"N/A, N/A", 0), (b"100, 50\n100, 50", 0), (b"100, 50", 1), (b"100, 101", 0)):
            child = SimpleNamespace(returncode=code, communicate=AsyncMock(return_value=(output, b"")))
            with patch("app.resources.Path.is_file", return_value=True), patch("app.resources.asyncio.create_subprocess_exec", new=AsyncMock(return_value=child)):
                self.assertIsNone(await gpu_memory())

    async def test_gpu_timeout_and_cancellation_reap_the_child(self) -> None:
        """Even an interrupted diagnostic must not leave a subprocess orphaned."""

        for error in (TimeoutError(), asyncio.CancelledError()):
            child = SimpleNamespace(returncode=None, kill=Mock(), communicate=AsyncMock(side_effect=[error, (b"", b"")]))
            with patch("app.resources.Path.is_file", return_value=True), patch("app.resources.asyncio.create_subprocess_exec", new=AsyncMock(return_value=child)):
                if isinstance(error, asyncio.CancelledError):
                    with self.assertRaises(asyncio.CancelledError):
                        await gpu_memory()
                else:
                    self.assertIsNone(await gpu_memory())
                child.kill.assert_called_once()
                self.assertEqual(child.communicate.await_count, 2)

    async def test_missing_gpu_and_docker_are_honest_and_gpu_is_cached(self) -> None:
        """No NVIDIA reading becomes fictitious zero; no unavailable service is started."""

        self.services.update(docker_available=False)
        monitor = ResourceMonitor(self.policy, AsyncMock(return_value=self.services))
        with patch("app.resources.gpu_memory", new=AsyncMock(return_value=None)) as gpu, patch.object(monitor.counters, "sample", return_value=(None, None)):
            for _ in range(3):
                result = await monitor.sample()
                self.assertIsNone(result["ram"])
                self.assertIsNone(result["vram"])
                self.assertEqual(result["level"], "WARNING")
            self.assertEqual(gpu.call_count, 1)

    async def test_probe_failure_does_not_publish_healthy_or_keep_orphan_task(self) -> None:
        """A failed sampler yields an explicitly stale snapshot and still shuts down."""

        monitor = ResourceMonitor(self.policy, AsyncMock(side_effect=RuntimeError("private")))
        with patch("app.resources.gpu_memory", new=AsyncMock(return_value=None)):
            monitor.set_active(True)
            monitor.start()
            await asyncio.sleep(0.03)
            self.assertTrue(monitor.snapshot()["stale"])
            await monitor.close()

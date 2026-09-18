from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.checkpoints import CheckpointService  # noqa: E402
from app.database import Database  # noqa: E402
from app.model_registry import load_model_registry  # noqa: E402
from app.openhands_runs import OpenHandsRunManager  # noqa: E402
from app.openhands_runtime import AGENT_SERVER_MODE_IDLE, AGENT_SERVER_MODE_RUN, AgentServerHandle  # noqa: E402
from app.workspace import WorkspaceGuard  # noqa: E402


class FakeProcess:
    """Model an SDK child process whose termination is controlled by the manager test."""

    def __init__(self, *, finished: bool) -> None:
        """Optionally finish immediately or wait until cancel asks the fake process to stop."""

        self.returncode: int | None = 0 if finished else None
        self._completed = asyncio.Event()
        if finished:
            self._completed.set()

    async def wait(self) -> int:
        """Wait until the deterministic fake process reaches a return code."""

        await self._completed.wait()
        return int(self.returncode or 0)

    def terminate(self) -> None:
        """Model graceful SDK process termination requested by cancellation."""

        self.returncode = -15
        self._completed.set()

    def kill(self) -> None:
        """Model forced process termination when graceful shutdown exceeds its bound."""

        self.returncode = -9
        self._completed.set()


class FakeRuntime:
    """Record only manager-owned Agent Server calls without starting Docker in unit tests."""

    def __init__(self) -> None:
        """Initialize a stable local endpoint and ordered lifecycle call log."""

        self.agent_server_url = "http://127.0.0.1:18010"
        self.started_paths: list[Path | None] = []
        self.stopped: list[str] = []
        self.recovered_paths: list[Path] = []
        self.recovery_handle: AgentServerHandle | None = None
        self.mutate_project_on_run = False

    async def stop_idle_agent_server(self) -> None:
        """Record that the idle no-project server yielded the fixed loopback port."""

        self.stopped.append("idle")

    async def start_agent_server(
        self, *, run_id: str | None = None, project_path: Path | None = None
    ) -> AgentServerHandle:
        """Return a handle tied to the exact test path supplied by the frozen run."""

        self.started_paths.append(project_path)
        if run_id is None:
            return AgentServerHandle("idle-container", "idle", None, None, AGENT_SERVER_MODE_IDLE)
        if self.mutate_project_on_run and project_path is not None:
            (project_path / "main.py").write_text("value = 2\n", encoding="utf-8")
        return AgentServerHandle(
            "run-container",
            f"run-{run_id}",
            run_id,
            project_path,
            AGENT_SERVER_MODE_RUN,
        )

    async def stop_agent_server(self, handle: AgentServerHandle) -> None:
        """Record the exact run container stop before the manager writes terminal SQLite state."""

        self.stopped.append(handle.container_id)

    async def find_run_agent_server(
        self, _run_id: str, project_path: Path
    ) -> AgentServerHandle | None:
        """Record recovery mount verification and optionally return one test-owned container."""

        self.recovered_paths.append(project_path)
        return self.recovery_handle


class FakeStarter:
    """Create deterministic SDK result files instead of invoking the real SDK during unit tests."""

    def __init__(
        self,
        *,
        finished: bool,
        tool_names: object = None,
        validation_status: object = "validated",
    ) -> None:
        """Choose a terminal fake result and the JSON tool evidence it publishes."""

        self.finished = finished
        self.tool_names = ["terminal", "file_editor"] if tool_names is None else tool_names
        self.validation_status = validation_status

    async def __call__(self, *arguments: str, **_kwargs: Any) -> FakeProcess:
        """Write the owned JSON result paths passed by the manager before returning a fake child."""

        values = list(arguments)
        result_path = Path(values[values.index("--result-path") + 1])
        session_path = Path(values[values.index("--session-path") + 1])
        run_id = values[values.index("--run-id") + 1]
        session_id = f"sdk-{run_id}"
        session_path.write_text(json.dumps({"run_id": run_id, "session_id": session_id}), encoding="utf-8")
        if self.finished:
            result_path.write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "session_id": session_id,
                        "state": "completed",
                        "execution_status": "finished",
                        "result_summary": "Tests verts après une correction réelle.",
                        "tool_names": self.tool_names,
                        "validation_status": self.validation_status,
                    }
                ),
                encoding="utf-8",
            )
        return FakeProcess(finished=self.finished)


class OpenHandsRunManagerTests(unittest.IsolatedAsyncioTestCase):
    """Prove frozen-project persistence and cancellation ordering without Docker or Qwen."""

    def setUp(self) -> None:
        """Create two selectable projects so a later active-project change can be tested safely."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-openhands-run-test-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.workspace_root = self.base / "IA_WORKSPACE"
        for name in ("First", "Second"):
            project = self.workspace_root / name
            project.mkdir(parents=True)
            (project / "main.py").write_text("value = 1\n", encoding="utf-8")
        self.database = Database(self.base / "lea.sqlite3")
        self.database.initialize()
        self.projects = self.database.sync_projects([("First", "First"), ("Second", "Second")])
        self.guard = WorkspaceGuard(self.workspace_root)
        self.checkpoints = CheckpointService(self.database, self.guard, self.base / "checkpoints")
        self.registry = load_model_registry()
        self.finished_calls = 0

    def tearDown(self) -> None:
        """Remove the temporary workspace after the manager has finished every fake child process."""

        self.temporary_directory.cleanup()

    async def finished_callback(self) -> None:
        """Record one coordinator release after a truly terminal manager lifecycle."""

        self.finished_calls += 1

    def manager(
        self,
        *,
        finished: bool,
        tool_names: object = None,
        validation_status: object = "validated",
    ) -> tuple[OpenHandsRunManager, FakeRuntime]:
        """Build a manager with a fake Agent Server and deterministic SDK subprocess starter."""

        runtime = FakeRuntime()
        return (
            OpenHandsRunManager(
                self.database,
                self.guard,
                self.checkpoints,
                runtime,  # type: ignore[arg-type]
                self.registry,
                self.base / "run-state",
                process_starter=FakeStarter(
                    finished=finished,
                    tool_names=tool_names,
                    validation_status=validation_status,
                ),
            ),
            runtime,
        )

    async def test_finished_run_keeps_its_frozen_project_after_active_selection_changes(self) -> None:
        """The run database row and Docker mount remain First even when Second becomes globally active."""

        manager, runtime = self.manager(finished=True)
        first = self.projects[0]
        frozen = self.guard.freeze_project(first["id"], first["relative_path"])
        record = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)
        self.database.activate_project(self.projects[1]["id"])
        final = await manager.wait_for_completion(record["run_id"])

        self.assertEqual(final["state"], "completed")
        self.assertEqual(final["validation_status"], "validated")
        self.assertEqual(final["project_id"], first["id"])
        self.assertEqual(runtime.started_paths[0], frozen.workspace_path.path)
        self.assertIn("run-container", runtime.stopped)
        self.assertEqual(self.finished_calls, 1)

    async def test_cancel_publishes_cancelled_only_after_the_run_container_stops(self) -> None:
        """Cancellation terminates the SDK client, stops the container, snapshots, then updates SQLite."""

        manager, runtime = self.manager(finished=False)
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        record = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)
        cancelled = await manager.cancel(record["run_id"])

        self.assertEqual(cancelled["state"], "cancelled")
        self.assertIn("run-container", runtime.stopped)
        self.assertEqual(self.finished_calls, 1)

    async def test_completed_runner_without_project_tool_evidence_is_failed(self) -> None:
        """A technical child stop without project evidence is an explicit failure."""

        for tool_names in ([], ["task_tracker", "finish"], "terminal"):
            with self.subTest(tool_names=tool_names):
                manager, runtime = self.manager(finished=True, tool_names=tool_names)
                project = self.projects[0]
                frozen = self.guard.freeze_project(project["id"], project["relative_path"])
                record = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)
                final = await manager.wait_for_completion(record["run_id"])

                self.assertEqual(final["state"], "failed")
                self.assertEqual(final["validation_status"], "failed")
                self.assertIn("run-container", runtime.stopped)

    async def test_completed_runner_with_verified_evidence_is_validated(self) -> None:
        """The manager preserves the runner's explicit validated evidence verdict."""

        manager, _runtime = self.manager(finished=True, tool_names=["terminal"])
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        record = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)

        final = await manager.wait_for_completion(record["run_id"])
        self.assertEqual(final["state"], "completed")
        self.assertEqual(final["validation_status"], "validated")

    async def test_legacy_completed_child_without_validation_verdict_is_failed(self) -> None:
        """A malformed or older result cannot silently acquire a success status."""

        manager, _runtime = self.manager(
            finished=True,
            validation_status=None,
        )
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        record = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)

        final = await manager.wait_for_completion(record["run_id"])
        self.assertEqual(final["state"], "failed")
        self.assertEqual(final["validation_status"], "failed")

    async def test_second_run_after_rollback_uses_a_new_session_and_the_restored_source_tree(self) -> None:
        """Rollback cannot leak the first run's session or mutated source state into its successor."""

        manager, runtime = self.manager(finished=True)
        runtime.mutate_project_on_run = True
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        first = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)
        first_final = await manager.wait_for_completion(first["run_id"])

        self.assertEqual((frozen.workspace_path.path / "main.py").read_text(encoding="utf-8"), "value = 2\n")
        self.checkpoints.rollback(str(first_final["checkpoint_id"]), frozen)
        self.assertEqual((frozen.workspace_path.path / "main.py").read_text(encoding="utf-8"), "value = 1\n")

        second = await manager.start("Corrige main.py", self.registry.profile("development"), frozen, self.finished_callback)
        second_final = await manager.wait_for_completion(second["run_id"])

        self.assertNotEqual(first_final["run_id"], second_final["run_id"])
        self.assertNotEqual(first_final["openhands_session_id"], second_final["openhands_session_id"])
        self.assertNotEqual(first_final["checkpoint_id"], second_final["checkpoint_id"])
        self.assertTrue((manager._run_directory(first_final["run_id"], create=False) / "task.txt").is_file())
        self.assertTrue((manager._run_directory(second_final["run_id"], create=False) / "task.txt").is_file())
        self.assertEqual((frozen.workspace_path.path / "main.py").read_text(encoding="utf-8"), "value = 2\n")

    async def test_restart_recovery_finalizes_an_interrupted_run_and_keeps_its_checkpoint_usable(self) -> None:
        """A persisted in-flight run becomes a truthful failed record after its owned server is absent."""

        manager, _runtime = self.manager(finished=True)
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        run_id = "123e4567-e89b-42d3-a456-426614174000"
        self.database.create_agent_run(run_id, frozen.project_id, "development", "Corrige main.py", state="running")
        checkpoint = self.checkpoints.create(run_id, frozen)

        await manager.recover()

        self.assertEqual(self.database.get_agent_run(run_id)["state"], "failed")
        self.assertEqual(
            self.database.get_project_checkpoint(str(checkpoint["checkpoint_id"]))["state"],
            "completed",
        )

    async def test_restart_recovery_stops_the_owned_container_before_marking_a_replaced_project_conflict(self) -> None:
        """Recovery derives its mount from the checkpoint, not a mutable project catalog entry."""

        manager, runtime = self.manager(finished=True)
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        run_id = "123e4567-e89b-42d3-a456-426614174001"
        self.database.create_agent_run(run_id, frozen.project_id, "development", "Corrige main.py", state="running")
        checkpoint = self.checkpoints.create(run_id, frozen)
        (frozen.workspace_path.path / "main.py").write_text("value = 2\n", encoding="utf-8")
        self.checkpoints.complete(str(checkpoint["checkpoint_id"]), frozen)
        archived = self.workspace_root / "First-original"
        frozen.workspace_path.path.rename(archived)
        frozen.workspace_path.path.mkdir()
        (frozen.workspace_path.path / "main.py").write_text("replacement = True\n", encoding="utf-8")
        self.database.sync_projects([("Second", "Second")])
        runtime.recovery_handle = AgentServerHandle(
            "recovered-container",
            f"run-{run_id}",
            run_id,
            frozen.workspace_path.path,
            AGENT_SERVER_MODE_RUN,
        )

        await manager.recover()

        self.assertEqual(runtime.recovered_paths, [self.workspace_root / "First"])
        self.assertIn("recovered-container", runtime.stopped)
        self.assertEqual(self.database.get_agent_run(run_id)["state"], "failed")
        self.assertEqual(
            self.database.get_project_checkpoint(str(checkpoint["checkpoint_id"]))["state"],
            "conflict",
        )
        self.assertEqual(
            (self.workspace_root / "First" / "main.py").read_text(encoding="utf-8"),
            "replacement = True\n",
        )

    async def test_restart_recovery_marks_a_deleted_ready_project_failed_after_verified_absence(self) -> None:
        """A vanished project never blocks recovery on the mutable project synchronization table."""

        manager, runtime = self.manager(finished=True)
        project = self.projects[0]
        frozen = self.guard.freeze_project(project["id"], project["relative_path"])
        run_id = "123e4567-e89b-42d3-a456-426614174002"
        self.database.create_agent_run(run_id, frozen.project_id, "development", "Corrige main.py", state="running")
        checkpoint = self.checkpoints.create(run_id, frozen)
        shutil.rmtree(frozen.workspace_path.path)
        self.database.sync_projects([("Second", "Second")])

        await manager.recover()

        self.assertEqual(runtime.recovered_paths, [self.workspace_root / "First"])
        self.assertEqual(self.database.get_agent_run(run_id)["state"], "failed")
        self.assertEqual(
            self.database.get_project_checkpoint(str(checkpoint["checkpoint_id"]))["state"],
            "failed",
        )


if __name__ == "__main__":
    unittest.main()

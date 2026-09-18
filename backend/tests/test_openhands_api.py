from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.checkpoints import CheckpointService  # noqa: E402
from app.main import create_app  # noqa: E402
from app.memory import parse_memory_command  # noqa: E402
from app.model_registry import load_model_registry  # noqa: E402
from app.openhands_runs import OpenHandsRunManager  # noqa: E402
from app.openhands_runtime import AGENT_SERVER_MODE_IDLE, AGENT_SERVER_MODE_RUN, AgentServerHandle  # noqa: E402


class FakeModelController:
    """Confirm profile switches without starting any real model during API contract tests."""

    async def activate(self, profile_id: str) -> str:
        """Return the requested known profile exactly as a successful local controller would."""

        return profile_id


class FinishedProcess:
    """Represent an SDK process that already produced its atomic result file."""

    def __init__(self) -> None:
        """Set the fake child return code to a completed value immediately."""

        self.returncode: int | None = 0

    async def wait(self) -> int:
        """Return immediately because this deterministic runner already ended."""

        return 0

    def terminate(self) -> None:
        """Keep the protocol compatible with a manager cancellation path."""

        self.returncode = -15

    def kill(self) -> None:
        """Keep the protocol compatible with an escalation cancellation path."""

        self.returncode = -9


class FakeRuntime:
    """Provide only verified lifecycle handles, never Docker, to the HTTP route test."""

    def __init__(self) -> None:
        """Expose the registry loopback endpoint used to construct the runner command."""

        self.agent_server_url = "http://127.0.0.1:18010"
        self.stopped: list[str] = []
        self.mutate_project_during_run = False

    async def stop_idle_agent_server(self) -> None:
        """Record release of the idle server before the fake run server starts."""

        self.stopped.append("idle")

    async def start_agent_server(
        self, *, run_id: str | None = None, project_path: Path | None = None
    ) -> AgentServerHandle:
        """Return an immutable handle associated with the exact frozen path supplied by the manager."""

        if run_id is None:
            return AgentServerHandle("idle", "idle", None, None, AGENT_SERVER_MODE_IDLE)
        if self.mutate_project_during_run and project_path is not None:
            # This replaces the real SDK edit only inside the fake HTTP test,
            # so the manager must persist a genuine before/after checkpoint.
            (project_path / "main.py").write_text("value = 2\n", encoding="utf-8")
        return AgentServerHandle("run", f"run-{run_id}", run_id, project_path, AGENT_SERVER_MODE_RUN)

    async def stop_agent_server(self, handle: AgentServerHandle) -> None:
        """Record container stop before the manager publishes a terminal SQLite row."""

        self.stopped.append(handle.container_id)


class FinishedStarter:
    """Write the minimal SDK output needed to test the final HTTP persistence surface."""

    def __init__(self, validation_status: object = "validated") -> None:
        """Choose the child evidence verdict without bypassing the real manager lifecycle."""

        self.validation_status = validation_status

    async def __call__(self, *arguments: str, **_kwargs: Any) -> FinishedProcess:
        """Place session and result JSON at the backend-owned paths passed to the runner."""

        values = list(arguments)
        run_id = values[values.index("--run-id") + 1]
        session_path = Path(values[values.index("--session-path") + 1])
        result_path = Path(values[values.index("--result-path") + 1])
        session_path.write_text(json.dumps({"run_id": run_id, "session_id": "sdk-session"}), encoding="utf-8")
        result_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "session_id": "sdk-session",
                    "state": "completed",
                    "execution_status": "finished",
                    "result_summary": "Correction testée et finalisée.",
                    "tool_names": ["terminal", "file_editor"],
                    "validation_status": self.validation_status,
                }
            ),
            encoding="utf-8",
        )
        return FinishedProcess()


class OpenHandsApiTests(unittest.TestCase):
    """Exercise the public Programming run, diff, rollback, and SQLite routes with fake local services."""

    def setUp(self) -> None:
        """Start FastAPI with a temporary workspace, then substitute only its test-owned run manager."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-openhands-api-test-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.workspace = self.base / "IA_WORKSPACE"
        project = self.workspace / "Example"
        project.mkdir(parents=True)
        (project / "main.py").write_text("value = 1\n", encoding="utf-8")
        self.application = create_app(
            database_path=self.base / "lea.sqlite3",
            model_gateway=object(),
            model_controller=FakeModelController(),
            workspace_root=self.workspace,
            checkpoint_root=self.base / "checkpoints",
            agent_runtime_root=self.base / "runs",
        )
        self.context = TestClient(self.application)
        self.client = self.context.__enter__()
        self.runtime = FakeRuntime()
        self.application.state.openhands_runs = OpenHandsRunManager(
            self.application.state.database,
            self.application.state.workspace_guard,
            CheckpointService(
                self.application.state.database,
                self.application.state.workspace_guard,
                self.base / "checkpoints",
            ),
            self.runtime,  # type: ignore[arg-type]
            load_model_registry(),
            self.base / "runs",
            process_starter=FinishedStarter(),
        )

    def tearDown(self) -> None:
        """Close FastAPI before removing temporary SQLite, checkpoint, and runner files."""

        self.context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def wait_for_final(self, run_id: str) -> dict[str, Any]:
        """Poll the actual HTTP route until the manager has stopped the fake server and committed SQLite."""

        for _ in range(50):
            response = self.client.get(f"/api/agent-runs/{run_id}")
            self.assertEqual(response.status_code, 200)
            run = response.json()
            if run["state"] in {"completed", "failed", "cancelled", "limit_reached"}:
                return run
            time.sleep(0.02)
        self.fail("Le run OpenHands factice n'a pas atteint un état terminal.")

    def test_programming_run_is_persisted_and_can_be_rolled_back_through_the_api(self) -> None:
        """The UI contract starts one frozen run and exposes its post-run checkpoint without direct file tools."""

        origin = {"Origin": "http://127.0.0.1:5173"}
        self.runtime.mutate_project_during_run = True
        self.assertEqual(self.client.post("/api/models/development/activate", headers=origin).status_code, 200)
        project_id = self.client.get("/api/projects").json()["projects"][0]["id"]
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/activate", headers=origin).status_code, 200)

        started = self.client.post("/api/agent-runs", json={"task": "Corrige main.py"}, headers=origin)
        self.assertEqual(started.status_code, 202)
        final = self.wait_for_final(started.json()["run_id"])
        self.assertEqual(final["state"], "completed")
        self.assertEqual(final["validation_status"], "validated")
        self.assertEqual(final["project_id"], project_id)
        self.assertEqual(final["openhands_session_id"], "sdk-session")
        self.assertIn("run", self.runtime.stopped)

        changes = self.client.get(f"/api/agent-runs/{final['run_id']}/changes")
        self.assertEqual(changes.status_code, 200)
        self.assertEqual(changes.json()["checkpoint"]["state"], "completed")
        self.assertEqual(changes.json()["changes"], [{"relative_path": "main.py", "entry_type": "file", "change": "modified"}])
        self.assertEqual((self.workspace / "Example" / "main.py").read_text(encoding="utf-8"), "value = 2\n")
        rollback = self.client.post(f"/api/agent-runs/{final['run_id']}/rollback", headers=origin)
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual(rollback.json()["checkpoint"]["state"], "rolled_back")
        self.assertEqual((self.workspace / "Example" / "main.py").read_text(encoding="utf-8"), "value = 1\n")

    def test_completed_run_memory_and_conversation_survive_fastapi_restart_with_a_working_rollback(self) -> None:
        """SQLite keeps the compact run and stage-9 data coherent across a real app reconstruction."""

        origin = {"Origin": "http://127.0.0.1:5173"}
        self.runtime.mutate_project_during_run = True
        database = self.application.state.database
        conversation_id, user_message_id = database.create_pending_conversation("Avant redémarrage")
        database.complete_generation(conversation_id, user_message_id, "Réponse conservée")
        command = parse_memory_command("Retiens que le nonce persistant est 10I-test.")
        self.assertIsNotNone(command)
        database.apply_memory_command(
            command,  # type: ignore[arg-type]
            "Retiens que le nonce persistant est 10I-test.",
            conversation_id,
            database.get_conversation(conversation_id)["revision"],
        )
        self.assertEqual(self.client.post("/api/models/development/activate", headers=origin).status_code, 200)
        project_id = self.client.get("/api/projects").json()["projects"][0]["id"]
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/activate", headers=origin).status_code, 200)
        started = self.client.post("/api/agent-runs", json={"task": "Corrige main.py"}, headers=origin)
        self.assertEqual(started.status_code, 202)
        final = self.wait_for_final(started.json()["run_id"])
        self.assertEqual(final["state"], "completed")
        self.assertEqual((self.workspace / "Example" / "main.py").read_text(encoding="utf-8"), "value = 2\n")

        # Closing then rebuilding TestClient executes FastAPI's real lifespan
        # instead of merely reusing a manager or a SQLite connection in memory.
        self.context.__exit__(None, None, None)
        self.application = create_app(
            database_path=self.base / "lea.sqlite3",
            model_gateway=object(),
            model_controller=FakeModelController(),
            workspace_root=self.workspace,
            checkpoint_root=self.base / "checkpoints",
            agent_runtime_root=self.base / "runs",
        )
        self.context = TestClient(self.application)
        self.client = self.context.__enter__()

        persisted = self.client.get(f"/api/agent-runs/{final['run_id']}")
        self.assertEqual(persisted.status_code, 200)
        self.assertEqual(persisted.json()["result_summary"], final["result_summary"])
        changes = self.client.get(f"/api/agent-runs/{final['run_id']}/changes")
        self.assertEqual(changes.status_code, 200)
        self.assertEqual(changes.json()["checkpoint"]["state"], "completed")
        self.assertEqual(changes.json()["changes"][0]["relative_path"], "main.py")
        self.assertEqual(
            self.client.get(f"/api/conversations/{conversation_id}").json()["messages"][1]["content"],
            "Réponse conservée",
        )
        self.assertEqual(
            self.application.state.database.list_memories()[0]["content"],
            "le nonce persistant est 10I-test.",
        )
        rollback = self.client.post(f"/api/agent-runs/{final['run_id']}/rollback", headers=origin)
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual(rollback.json()["checkpoint"]["state"], "rolled_back")
        self.assertEqual((self.workspace / "Example" / "main.py").read_text(encoding="utf-8"), "value = 1\n")

    def test_api_persists_acceptance_and_refuses_rollback_afterward(self) -> None:
        """The explicit user acceptance route makes a completed checkpoint permanently non-restorable."""

        origin = {"Origin": "http://127.0.0.1:5173"}
        self.runtime.mutate_project_during_run = True
        self.assertEqual(self.client.post("/api/models/development/activate", headers=origin).status_code, 200)
        project_id = self.client.get("/api/projects").json()["projects"][0]["id"]
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/activate", headers=origin).status_code, 200)
        started = self.client.post("/api/agent-runs", json={"task": "Corrige main.py"}, headers=origin)
        final = self.wait_for_final(started.json()["run_id"])

        accepted = self.client.post(f"/api/agent-runs/{final['run_id']}/accept", headers=origin)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["checkpoint"]["state"], "accepted")
        self.assertEqual(
            self.client.post(f"/api/agent-runs/{final['run_id']}/rollback", headers=origin).status_code,
            409,
        )
        self.assertEqual((self.workspace / "Example" / "main.py").read_text(encoding="utf-8"), "value = 2\n")

    def test_api_marks_an_unverified_child_failed_and_keeps_it_rollbackable(self) -> None:
        """A compact child result without proof is failed, rollbackable, and not acceptable."""

        origin = {"Origin": "http://127.0.0.1:5173"}
        self.runtime.mutate_project_during_run = True
        self.application.state.openhands_runs._process_starter = FinishedStarter("unverified")
        self.assertEqual(self.client.post("/api/models/development/activate", headers=origin).status_code, 200)
        project_id = self.client.get("/api/projects").json()["projects"][0]["id"]
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/activate", headers=origin).status_code, 200)
        started = self.client.post("/api/agent-runs", json={"task": "Corrige main.py"}, headers=origin)
        final = self.wait_for_final(started.json()["run_id"])

        self.assertEqual(final["state"], "failed")
        self.assertEqual(final["validation_status"], "failed")
        self.assertEqual(self.client.post(f"/api/agent-runs/{final['run_id']}/accept", headers=origin).status_code, 409)
        rollback = self.client.post(f"/api/agent-runs/{final['run_id']}/rollback", headers=origin)
        self.assertEqual(rollback.status_code, 200)
        self.assertEqual((self.workspace / "Example" / "main.py").read_text(encoding="utf-8"), "value = 1\n")

    def test_api_rejects_a_same_name_project_replacement_and_exposes_the_conflict(self) -> None:
        """The rollback route compares the checkpoint identity before touching a replacement project."""

        origin = {"Origin": "http://127.0.0.1:5173"}
        self.runtime.mutate_project_during_run = True
        self.assertEqual(self.client.post("/api/models/development/activate", headers=origin).status_code, 200)
        project_id = self.client.get("/api/projects").json()["projects"][0]["id"]
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/activate", headers=origin).status_code, 200)
        started = self.client.post("/api/agent-runs", json={"task": "Corrige main.py"}, headers=origin)
        final = self.wait_for_final(started.json()["run_id"])
        project_path = self.workspace / "Example"
        project_path.rename(self.workspace / "Example-original")
        project_path.mkdir()
        (project_path / "main.py").write_text("replacement = True\n", encoding="utf-8")

        rollback = self.client.post(f"/api/agent-runs/{final['run_id']}/rollback", headers=origin)
        self.assertEqual(rollback.status_code, 409)
        changes = self.client.get(f"/api/agent-runs/{final['run_id']}/changes")
        self.assertEqual(changes.status_code, 200)
        self.assertEqual(changes.json()["checkpoint"]["state"], "conflict")
        self.assertEqual((project_path / "main.py").read_text(encoding="utf-8"), "replacement = True\n")


if __name__ == "__main__":
    unittest.main()

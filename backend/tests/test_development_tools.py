from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from pydantic import ValidationError


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.database import Database  # noqa: E402
from app.development_tools import (  # noqa: E402
    DEVELOPMENT_ARGUMENT_MODELS,
    MAX_PROCESS_OUTPUT_BYTES,
    DevelopmentToolError,
    DevelopmentToolExecutor,
)
from app.workspace import WorkspaceGuard, WorkspacePathError  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Les commandes contrôlées ciblent Windows.")
class DevelopmentToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    """Valide les commandes haut niveau sans exposer d'argv fourni librement."""

    def setUp(self) -> None:
        """Crée un projet Node/Git temporaire avec scripts entièrement déclarés."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-dev-tools-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.workspace = self.base / "IA_WORKSPACE"
        self.project = self.workspace / "Projet"
        self.project.mkdir(parents=True)
        scripts = {
            "build": "node -e \"console.log('BUILD_OK')\"",
            "test": "node -e \"console.log('TEST_OK')\"",
            "lint": "node -e \"console.log('LINT_OK')\"",
            "typecheck": "node -e \"console.log('TYPECHECK_OK')\"",
            "echo-safe": "node -e \"console.log('NAMED_OK')\"",
            "flood": "node -e \"console.log('x'.repeat(100000))\"",
            "hang": "node -e \"setInterval(() => {}, 1000)\"",
            "dev": "node -e \"setInterval(() => {}, 1000)\"",
            "environment": "node -e \"console.log((process.env.LEA_SECRET_TEST || 'CLEAN') + ':' + process.env.NPM_CONFIG_OFFLINE)\"",
        }
        (self.project / "package.json").write_text(
            json.dumps({"name": "temporary-project", "scripts": scripts}, indent=2),
            encoding="utf-8",
        )
        (self.project / "app.js").write_text("console.log('v1')\n", encoding="utf-8")
        git = shutil.which("git")
        if git is None:
            self.skipTest("Git n'est pas installé.")
        commands = (
            [git, "init"],
            [git, "add", "app.js", "package.json"],
            [git, "-c", "user.name=Léa Test", "-c", "user.email=lea@example.invalid", "commit", "-m", "initial"],
        )
        for command in commands:
            result = subprocess.run(command, cwd=self.project, capture_output=True, check=False)
            if result.returncode != 0:
                self.skipTest(f"Initialisation Git indisponible : {result.stderr!r}")
        (self.project / "app.js").write_text("console.log('v2')\n", encoding="utf-8")

        self.database = Database(self.base / "lea.sqlite3")
        self.database.initialize()
        project = self.database.sync_projects([("Projet", "Projet")])[0]
        self.database.activate_project(project["id"])
        self.executor = DevelopmentToolExecutor(
            self.database,
            WorkspaceGuard(self.workspace),
            self.base / "runtime",
        )

    async def asyncTearDown(self) -> None:
        """Arrête tout enfant restant avant de supprimer le projet temporaire."""

        await self.executor.close()
        self.temporary_directory.cleanup()

    async def test_detection_catalog_and_declared_commands(self) -> None:
        """Node est détecté et build/tests/lint/typecheck restent des choix abstraits."""

        detection = await self.executor.execute("detect_project", {})
        self.assertTrue(detection["ecosystems"]["node"]["detected"])
        self.assertTrue(detection["ecosystems"]["node"]["tool_available"])
        self.assertIn("test", detection["ecosystems"]["node"]["scripts"])
        commands = await self.executor.execute("list_project_commands", {})
        command_ids = {command["id"] for command in commands["commands"]}
        self.assertTrue({"npm:build", "npm:test", "npm:lint", "npm:typecheck"} <= command_ids)
        self.assertTrue({"git:status", "git:diff", "git:diff-check", "git:log"} <= command_ids)
        self.assertEqual(set(DEVELOPMENT_ARGUMENT_MODELS), {
            "detect_project", "list_project_commands", "build_project", "run_tests",
            "run_linter", "run_typecheck", "run_named_script", "git_status",
            "git_diff", "git_diff_check", "git_log", "start_dev_server",
            "stop_dev_server",
        })

        for tool_name, marker in (
            ("build_project", "BUILD_OK"),
            ("run_tests", "TEST_OK"),
            ("run_linter", "LINT_OK"),
            ("run_typecheck", "TYPECHECK_OK"),
        ):
            with self.subTest(tool=tool_name):
                result = await self.executor.execute(tool_name, {"timeout_seconds": 20})
                self.assertEqual(result["exit_code"], 0, result)
                self.assertIn(marker, result["stdout"])

    async def test_named_script_is_exact_environment_is_clean_and_output_is_bounded(self) -> None:
        """Aucun métacaractère ne devient commande et les secrets ne sont pas hérités."""

        safe = await self.executor.execute(
            "run_named_script",
            {"script_name": "echo-safe", "timeout_seconds": 20},
        )
        self.assertEqual(safe["exit_code"], 0, safe)
        self.assertIn("NAMED_OK", safe["stdout"])
        with self.assertRaises(DevelopmentToolError):
            await self.executor.execute(
                "run_named_script",
                {"script_name": "echo-safe & whoami", "timeout_seconds": 20},
            )
        with self.assertRaises(ValidationError):
            await self.executor.execute(
                "run_named_script",
                {"script_name": "echo-safe", "arguments": ["--unsafe"]},
            )

        os.environ["LEA_SECRET_TEST"] = "SHOULD_NOT_LEAK"
        try:
            environment = await self.executor.execute(
                "run_named_script",
                {"script_name": "environment", "timeout_seconds": 20},
            )
        finally:
            os.environ.pop("LEA_SECRET_TEST", None)
        self.assertIn("CLEAN:true", environment["stdout"])
        flood = await self.executor.execute(
            "run_named_script",
            {"script_name": "flood", "timeout_seconds": 20},
        )
        self.assertTrue(flood["stdout_truncated"])
        self.assertLessEqual(len(flood["stdout"].encode("utf-8")), MAX_PROCESS_OUTPUT_BYTES)

    async def test_timeout_cancel_and_owned_server_tree(self) -> None:
        """Timeout, annulation et stop ne ciblent que les processus créés par l'exécuteur."""

        timeout = await self.executor.execute(
            "run_named_script",
            {"script_name": "hang", "timeout_seconds": 1},
        )
        self.assertTrue(timeout["timed_out"], timeout)

        run_id = str(uuid.uuid4())
        task = asyncio.create_task(
            self.executor.execute(
                "run_named_script",
                {"script_name": "hang", "timeout_seconds": 60},
                run_id=run_id,
            )
        )
        await asyncio.sleep(0.5)
        self.assertEqual(await self.executor.cancel_run(run_id), 1)
        cancelled_result = await asyncio.wait_for(task, timeout=10)
        self.assertNotEqual(cancelled_result["exit_code"], 0)

        server = await self.executor.execute(
            "start_dev_server",
            {"script_name": "dev"},
            run_id=str(uuid.uuid4()),
        )
        self.assertEqual(server["state"], "running")
        stopped = await self.executor.execute(
            "stop_dev_server",
            {"server_id": server["server_id"]},
        )
        self.assertEqual(stopped["state"], "stopped")
        with self.assertRaises(DevelopmentToolError):
            await self.executor.execute(
                "stop_dev_server",
                {"server_id": str(uuid.uuid4())},
            )

    async def test_git_is_read_only_bounded_and_path_validated(self) -> None:
        """Seuls status/diff/check/log sont accessibles avec un pathspec après `--`."""

        status = await self.executor.execute("git_status", {})
        self.assertEqual(status["exit_code"], 0)
        self.assertIn("app.js", status["stdout"])
        diff = await self.executor.execute(
            "git_diff",
            {"path": "app.js", "timeout_seconds": 20},
        )
        self.assertEqual(diff["exit_code"], 0)
        self.assertIn("v2", diff["stdout"])
        checked = await self.executor.execute(
            "git_diff_check",
            {"staged": False, "timeout_seconds": 20},
        )
        self.assertEqual(checked["exit_code"], 0)
        log = await self.executor.execute("git_log", {"limit": 1})
        self.assertEqual(log["exit_code"], 0)
        self.assertIn("initial", log["stdout"])
        with self.assertRaises(WorkspacePathError):
            await self.executor.execute(
                "git_diff",
                {"path": "..\\outside", "timeout_seconds": 20},
            )


if __name__ == "__main__":
    unittest.main()

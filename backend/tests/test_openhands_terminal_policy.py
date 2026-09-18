from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIRECTORY.parent
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.openhands_runtime import AGENT_TERMINAL_POLICY_SHA256  # noqa: E402


POLICY_PATH = PROJECT_ROOT / "tools" / "openhands" / "terminal_policy.py"


def terminal_event(command: str) -> str:
    """Build the native PreToolUse shape for one terminal command."""

    return json.dumps(
        {
            "event_type": "PreToolUse",
            "tool_name": "terminal",
            "tool_input": {"kind": "TerminalAction", "command": command},
        }
    )


def editor_event(command: str, path: Path, **fields: str) -> str:
    """Build the native PreToolUse shape for one editor action."""

    return json.dumps(
        {
            "event_type": "PreToolUse",
            "tool_name": "file_editor",
            "tool_input": {
                "kind": "FileEditorAction",
                "command": command,
                "path": str(path),
                **fields,
            },
        }
    )


class OpenHandsTerminalPolicyTests(unittest.TestCase):
    """Exercise the exact standalone hook mounted in the Agent Server."""

    def run_policy(
        self,
        payload: str,
        *,
        digest: str = AGENT_TERMINAL_POLICY_SHA256,
        workspace: Path | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
        """Run the policy with its integrity token and decode the verdict."""

        environment = os.environ.copy()
        environment["LEA_OPENHANDS_TERMINAL_POLICY_SHA256"] = digest
        if workspace is not None:
            environment["LEA_OPENHANDS_POLICY_WORKSPACE"] = str(workspace)
        result = subprocess.run(
            [sys.executable, str(POLICY_PATH)],
            input=payload,
            text=True,
            capture_output=True,
            env=environment,
            timeout=5,
            check=False,
        )
        return result, json.loads(result.stdout)

    def assert_denied(self, payload: str, *, workspace: Path | None = None) -> str:
        """Assert a fail-closed verdict and return its human-readable reason."""

        result, decision = self.run_policy(payload, workspace=workspace)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(decision["decision"], "deny")
        return decision["reason"]

    def test_checked_in_policy_matches_runtime_digest(self) -> None:
        """Prevent source drift between the verified file and its container mount."""

        digest = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, AGENT_TERMINAL_POLICY_SHA256)

    def test_local_reads_tests_and_git_status_are_allowed(self) -> None:
        """Preserve bounded inspection and validation inside the workspace."""

        for command in (
            "pwd",
            "cat README.md",
            "cd /workspace && python -m unittest -v",
            "npm test",
            "git status --short",
        ):
            with self.subTest(command=command):
                result, decision = self.run_policy(terminal_event(command))
                self.assertEqual(result.returncode, 0)
                self.assertEqual(decision, {"decision": "allow"})

    def test_digest_input_and_unknown_tools_fail_closed(self) -> None:
        """Reject an altered policy identity and tools outside the approved pair."""

        result, decision = self.run_policy(terminal_event("pwd"), digest="0" * 64)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(decision["decision"], "deny")
        self.assert_denied(json.dumps({"tool_name": "browser", "tool_input": {}}))

    def test_network_packages_mutable_git_and_shell_wrappers_are_denied(self) -> None:
        """Keep the offline run isolated from downloads and command indirection."""

        commands = (
            "curl https://example.com",
            "wget https://example.com/a",
            "pip install demo",
            "npm install",
            "git init",
            "git checkout -- source.py",
            "bash -c pwd",
            "env python -m unittest",
            "python -c 'print(1)'",
            "python -m http.server",
            "time curl https://example.com",
            "timeout 5 wget https://example.com/a",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_denied(terminal_event(command))

    def test_obfuscated_shell_escapes_are_denied(self) -> None:
        """Reject quote concatenation, expansion, assignments, and extra commands."""

        commands = (
            'g""it init',
            'c""url https://example.com',
            'p""ip install demo',
            "cat$IFS/etc/passwd",
            "X=/etc/passwd; cat $X",
            "echo $(pwd)",
            "echo `pwd`",
            "pwd; git status",
            "pwd | cat",
            "pwd\ncurl https://example.com",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_denied(terminal_event(command))

    def test_terminal_paths_cannot_escape_workspace(self) -> None:
        """Reject absolute host paths, traversal, home paths, and external cd."""

        for command in (
            "cat /etc/passwd",
            "cat /workspace/../etc/passwd",
            "cat ../../secret.txt",
            "cat ~/.ssh/id_rsa",
            "cd /tmp && pwd",
        ):
            with self.subTest(command=command):
                self.assert_denied(terminal_event(command))

    def test_native_tool_names_are_not_shell_commands(self) -> None:
        """Keep SDK tool calls on their authenticated native route."""

        self.assert_denied(terminal_event("file_editor view /workspace/source.py"))
        self.assert_denied(terminal_event("terminal pwd"))

    def test_source_sed_and_empty_source_creation_are_denied(self) -> None:
        """Keep source changes in content-bearing file-editor actions."""

        self.assert_denied(terminal_event("sed -i 's/a/b/' /workspace/source.py"))
        self.assert_denied(terminal_event("touch /workspace/source.ts"))

    def test_editor_is_confined_to_workspace(self) -> None:
        """Allow an in-project read while rejecting traversal and external paths."""

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            source = workspace / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            result, decision = self.run_policy(
                editor_event("view", source), workspace=workspace
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(decision, {"decision": "allow"})
            self.assert_denied(
                editor_event("view", workspace.parent / "secret.py"),
                workspace=workspace,
            )

    def test_tests_are_readable_but_immutable(self) -> None:
        """Expose specifications while denying every editor mutation of them."""

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            test_path = workspace / "tests" / "test_source.py"
            test_path.parent.mkdir()
            test_path.write_text("assert True\n", encoding="utf-8")
            result, decision = self.run_policy(
                editor_event("view", test_path), workspace=workspace
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(decision, {"decision": "allow"})
            reason = self.assert_denied(
                editor_event(
                    "str_replace",
                    test_path,
                    old_str="assert True",
                    new_str="assert False",
                ),
                workspace=workspace,
            )
            self.assertIn("immuables", reason)

    def test_editor_rejects_incomplete_and_noop_replacements(self) -> None:
        """Refuse malformed or ineffective structured replacements."""

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            source = workspace / "source.py"
            source.write_text("value = 1\n", encoding="utf-8")
            self.assert_denied(
                editor_event(
                    "str_replace", source, old_str="value = 1", new_str="value = 1"
                ),
                workspace=workspace,
            )
            self.assert_denied(
                editor_event("str_replace", source, old_str="value = 1"),
                workspace=workspace,
            )


if __name__ == "__main__":
    unittest.main()

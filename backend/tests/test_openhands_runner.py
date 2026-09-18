from __future__ import annotations

import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = PROJECT_ROOT / "tools" / "openhands" / "run_lea_agent.py"


class OpenHandsRunnerContractTests(unittest.TestCase):
    """Keep the runner on the official SDK and generic safety boundaries."""

    @classmethod
    def setUpClass(cls) -> None:
        """Parse the runner once for structural contract assertions."""

        cls.source = RUNNER_PATH.read_text(encoding="utf-8")
        cls.module = ast.parse(cls.source, filename=str(RUNNER_PATH))

    def function(self, name: str) -> ast.FunctionDef:
        """Return one top-level runner function by name."""

        return next(
            node
            for node in self.module.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        )

    def test_run_starts_the_sdk_loop_after_sending_the_task(self) -> None:
        """Require the official non-blocking SDK loop after the user message."""

        calls = [
            node
            for node in ast.walk(self.function("run"))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "conversation"
        ]
        sent = next(node for node in calls if node.func.attr == "send_message")
        started = next(node for node in calls if node.func.attr == "run")
        self.assertGreater(started.lineno, sent.lineno)
        self.assertTrue(
            any(
                keyword.arg == "blocking"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is False
                for keyword in started.keywords
            )
        )

    def test_runner_uses_only_authoritative_finish_evidence_publicly(self) -> None:
        """Keep intermediate model prose outside the public result boundary."""

        self.assertIn("evaluate_agent_history", self.source)
        self.assertIn("public_failure_summary", self.source)
        self.assertNotIn("assistant_message_summary", self.source)
        self.assertNotIn('event.get("kind") == "MessageEvent"', self.source)

    def test_runner_targets_only_the_frozen_workspace(self) -> None:
        """Bind SDK tools to the isolated project rather than server state."""

        self.assertIn(
            'Workspace(host=server_url, working_dir="/workspace")', self.source
        )
        self.assertIn("require_loopback_server", self.source)

    def test_only_validated_evidence_can_complete_a_run(self) -> None:
        """Map every invalid finished verdict to failed/failed."""

        self.assertIn('state = "failed"', self.source)
        self.assertIn('validation_status = "failed"', self.source)
        self.assertIn('state = "completed"', self.source)
        self.assertIn('validation_status = "validated"', self.source)
        self.assertNotIn('validation_status = "unverified"', self.source)

    def test_each_run_creates_a_fresh_conversation(self) -> None:
        """Prevent a later run from inheriting an earlier SDK conversation."""

        conversation_call = next(
            node
            for node in ast.walk(self.function("run"))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Conversation"
        )
        self.assertFalse(
            any(
                keyword.arg in {"id", "conversation_id"}
                for keyword in conversation_call.keywords
            )
        )

    def test_agent_keeps_serial_deterministic_native_tools(self) -> None:
        """Pin deterministic sampling and one native tool call at a time."""

        builder = self.function("build_agent")
        llm_call = next(
            node
            for node in ast.walk(builder)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "LLM"
        )
        keywords = {keyword.arg: keyword.value for keyword in llm_call.keywords}
        self.assertEqual(keywords["temperature"].value, 0.0)  # type: ignore[attr-defined]
        extra_body = keywords["litellm_extra_body"]
        self.assertIsInstance(extra_body, ast.Dict)
        values = {
            key.value: value.value
            for key, value in zip(extra_body.keys, extra_body.values, strict=True)
            if isinstance(key, ast.Constant)
            and isinstance(value, ast.Constant)
        }
        self.assertEqual(values["tool_choice"], "auto")
        self.assertIs(values["parallel_tool_calls"], False)
        self.assertIn("tool_concurrency_limit=1", self.source)

    def test_runner_uses_the_official_bounded_condenser(self) -> None:
        """Bound history with the SDK condenser rather than another agent loop."""

        self.assertIn("LLMSummarizingCondenser", self.source)
        self.assertIn("OPENHANDS_MINIMUM_CONTEXT_TOKENS = 16_384", self.source)
        self.assertIn("condenser=build_history_condenser(registry, llm)", self.source)
        self.assertIn('"native_tool_calling": False', self.source)

    def test_runner_uses_only_supported_stuck_configuration(self) -> None:
        """Avoid silently ignored per-pattern SDK settings."""

        conversation_call = next(
            node
            for node in ast.walk(self.function("run"))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Conversation"
        )
        keywords = {keyword.arg: keyword.value for keyword in conversation_call.keywords}
        self.assertNotIn("stuck_detection_thresholds", keywords)
        self.assertIs(keywords["stuck_detection"].value, False)  # type: ignore[attr-defined]
        self.assertIn(
            "max_iteration_per_run=registry.document.agent_policy.max_actions",
            self.source,
        )

    def test_both_native_tools_share_the_synchronous_local_policy(self) -> None:
        """Attach the verified PreToolUse hook to terminal and editor actions."""

        self.assertIn('matcher="terminal"', self.source)
        self.assertIn('matcher="file_editor"', self.source)
        self.assertEqual(self.source.count("command=AGENT_TERMINAL_POLICY_COMMAND"), 2)
        self.assertEqual(self.source.count("async_=False"), 2)
        self.assertIn("hook_config=build_local_tool_policy_hook_config()", self.source)

    def test_live_interruptions_use_only_generic_structured_signals(self) -> None:
        """Stop protocol denials and repeated editor cycles without task heuristics."""

        expected = (
            "has_blocked_terminal_policy_action",
            "has_successful_noop_file_editor_replacement",
            "has_repeated_hook_blocked_file_editor_replacement",
            "has_repeated_hook_blocked_immutable_test_edit",
            "has_repeated_failed_file_editor_view",
            "has_repeated_failed_file_editor_replacement",
            "has_repeated_failed_file_editor_retry_cycle",
            "has_repeated_successful_file_editor_view_cycle",
            "has_repeated_successful_file_editor_read_sweep",
            "has_repeated_successful_file_editor_expansion_cycle",
            "has_repeated_successful_file_editor_replacement_cycle",
        )
        for name in expected:
            self.assertIn(name, self.source)
        self.assertIn("conversation.interrupt()", self.source)

    def test_prompt_contract_is_generic_and_requires_exact_replacements(self) -> None:
        """Give the model reusable execution rules without benchmark solutions."""

        self.assertIn("PROTOCOLE BLOQUANT", self.source)
        self.assertIn("recopie old_str exactement", self.source)
        self.assertIn("ne répète jamais", self.source)
        self.assertIn("sans réseau", self.source)
        self.assertIn("FinishTool", self.source)

    def test_runner_contains_no_specialized_recovery_layer(self) -> None:
        """Keep difficult model decisions out of deterministic orchestration."""

        forbidden = (
            "inventory/models.py",
            "test_rejects_bool_as_numeric_value",
            "ModuleNotFoundError",
            "remediation_attempts",
            "build_noop_editor_recovery_prompt",
            "build_python_structural_recovery_prompt",
            "recoverable_",
            "MAX_SPECIALIZED",
        )
        for value in forbidden:
            self.assertNotIn(value, self.source)

    def test_failed_runs_keep_a_bounded_private_diagnostic(self) -> None:
        """Retain local reproducibility without leaking it into browser summaries."""

        self.assertIn("def private_error_summary", self.source)
        self.assertIn('"diagnostic": diagnostic', self.source)
        self.assertIn('"diagnostic": private_error_summary(error)', self.source)


if __name__ == "__main__":
    unittest.main()

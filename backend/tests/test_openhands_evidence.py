from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.openhands_evidence import (  # noqa: E402
    evaluate_agent_history,
    has_blocked_terminal_policy_action,
    has_repeated_failed_file_editor_replacement,
    has_repeated_failed_file_editor_retry_cycle,
    has_repeated_failed_file_editor_view,
    has_repeated_hook_blocked_file_editor_replacement,
    has_repeated_hook_blocked_immutable_test_edit,
    has_repeated_successful_file_editor_expansion_cycle,
    has_repeated_successful_file_editor_read_sweep,
    has_repeated_successful_file_editor_replacement_cycle,
    has_repeated_successful_file_editor_view_cycle,
    has_successful_noop_file_editor_replacement,
    public_failure_summary,
)


IMMUTABLE_TEST_REASON = (
    "Les tests sont immuables pendant un run Léa. Lis le test, puis crée "
    "ou corrige uniquement le module source attendu ; ne modifie jamais "
    "l'import ni l'attente du test."
)


def timestamp(index: int) -> str:
    """Create a stable server timestamp for chronological fixtures."""

    return f"2026-08-31T12:00:{index:02d}.000000Z"


def action(
    tool_name: str, call_id: str, payload: dict[str, object], index: int
) -> dict[str, object]:
    """Build one structured native ActionEvent."""

    kind = {
        "terminal": "TerminalAction",
        "file_editor": "FileEditorAction",
        "finish": "FinishAction",
    }[tool_name]
    return {
        "kind": "ActionEvent",
        "id": f"action-{call_id}",
        "timestamp": timestamp(index),
        "tool_name": tool_name,
        "tool_call_id": call_id,
        "action": {"kind": kind, **payload},
    }


def observation(
    tool_name: str,
    call_id: str,
    index: int,
    *,
    is_error: bool = False,
    exit_code: int = 0,
) -> dict[str, object]:
    """Build one correlated native ObservationEvent."""

    kind = {
        "terminal": "TerminalObservation",
        "file_editor": "FileEditorObservation",
        "finish": "FinishObservation",
    }[tool_name]
    result: dict[str, object] = {"kind": kind, "is_error": is_error}
    if tool_name == "terminal":
        result.update({"timeout": False, "exit_code": exit_code})
    return {
        "kind": "ObservationEvent",
        "id": f"observation-{call_id}",
        "timestamp": timestamp(index),
        "tool_name": tool_name,
        "tool_call_id": call_id,
        "action_id": f"action-{call_id}",
        "observation": result,
    }


def hook(
    tool_name: str, call_id: str, index: int, *, reason: str = "blocked"
) -> dict[str, object]:
    """Build one authenticated synchronous PreToolUse denial."""

    return {
        "kind": "HookExecutionEvent",
        "id": f"hook-{call_id}",
        "timestamp": timestamp(index),
        "hook_event_type": "PreToolUse",
        "tool_name": tool_name,
        "action_id": f"action-{call_id}",
        "blocked": True,
        "reason": reason,
    }


def finish(message: str, index: int) -> list[dict[str, object]]:
    """Build the required native FinishTool action and observation."""

    return [
        action("finish", f"finish-{index}", {"message": message}, index),
        observation("finish", f"finish-{index}", index + 1),
    ]


def replacement(call_id: str, index: int, old: str, new: str) -> list[dict[str, object]]:
    """Build one successful structured source replacement."""

    return [
        action(
            "file_editor",
            call_id,
            {
                "command": "str_replace",
                "path": "/workspace/source.py",
                "old_str": old,
                "new_str": new,
            },
            index,
        ),
        observation("file_editor", call_id, index + 1),
    ]


class OpenHandsEvidenceTests(unittest.TestCase):
    """Exercise only authenticated Agent Server history evidence."""

    def test_read_edit_green_test_and_finish_are_validated(self) -> None:
        """Accept a real project mutation followed by a green requested validation."""

        events = [
            action(
                "file_editor",
                "read",
                {"command": "view", "path": "/workspace/source.py"},
                1,
            ),
            observation("file_editor", "read", 2),
            *replacement("edit", 3, "return 0", "return 1"),
            action("terminal", "test", {"command": "python -m unittest -v"}, 5),
            observation("terminal", "test", 6),
            *finish("Source corrigé et test vert.", 7),
        ]

        evidence = evaluate_agent_history("Corrige puis lance les tests", events)

        self.assertTrue(evidence.validated)
        self.assertTrue(evidence.validation_required)
        self.assertTrue(evidence.validation_observed)
        self.assertEqual(evidence.tool_names, ("file_editor", "finish", "terminal"))

    def test_validation_must_follow_the_last_mutation(self) -> None:
        """Reject a green test made stale by a later successful write."""

        events = [
            action("terminal", "test", {"command": "python -m unittest"}, 1),
            observation("terminal", "test", 2),
            *replacement("edit", 3, "a", "b"),
            *finish("Terminé.", 5),
        ]
        evidence = evaluate_agent_history("Corrige et teste", events)
        self.assertFalse(evidence.validated)
        self.assertEqual(evidence.failure_code, "missing_post_mutation_validation")

    def test_finish_requires_a_successful_project_action(self) -> None:
        """Reject a bare FinishTool response without native project evidence."""

        evidence = evaluate_agent_history("Explique le projet", finish("Terminé.", 1))
        self.assertEqual(evidence.failure_code, "missing_project_action")

    def test_failed_editor_write_requires_reread_and_successful_retry(self) -> None:
        """Require current source evidence before accepting an edit retry."""

        failed = replacement("bad", 1, "missing", "fixed")
        failed[1] = observation("file_editor", "bad", 2, is_error=True)
        incomplete = [
            *failed,
            action("terminal", "test", {"command": "python -m unittest"}, 3),
            observation("terminal", "test", 4),
            *finish("Terminé.", 5),
        ]
        self.assertEqual(
            evaluate_agent_history("Corrige et teste", incomplete).failure_code,
            "unretried_file_editor_error",
        )

        recovered = [
            *failed,
            action(
                "file_editor",
                "read",
                {"command": "view", "path": "/workspace/source.py"},
                3,
            ),
            observation("file_editor", "read", 4),
            *replacement("good", 5, "current", "fixed"),
            action("terminal", "test", {"command": "python -m unittest"}, 7),
            observation("terminal", "test", 8),
            *finish("Corrigé et testé.", 9),
        ]
        self.assertTrue(evaluate_agent_history("Corrige et teste", recovered).validated)

    def test_missing_success_flag_and_malformed_security_events_fail_closed(self) -> None:
        """Never infer success or ignore malformed hooks and agent errors."""

        events = [
            action("terminal", "test", {"command": "python -m unittest"}, 1),
            observation("terminal", "test", 2),
            *finish("Terminé.", 3),
        ]
        del events[1]["observation"]["is_error"]  # type: ignore[index]
        self.assertFalse(evaluate_agent_history("Lance les tests", events).validated)

        for kind in ("HookExecutionEvent", "AgentErrorEvent"):
            malformed = {
                "kind": kind,
                "timestamp": timestamp(1),
                "tool_name": "terminal",
            }
            with self.subTest(kind=kind):
                evidence = evaluate_agent_history("Teste", [malformed, *finish("Fini.", 2)])
                self.assertEqual(evidence.failure_code, "history_unavailable")

    def test_terminal_policy_denial_is_a_public_failure(self) -> None:
        """Propagate an authenticated safety denial without trusting its prose."""

        events = [
            action("terminal", "network", {"command": "curl https://example.com"}, 1),
            hook("terminal", "network", 2),
            *finish("Terminé.", 3),
        ]
        self.assertTrue(has_blocked_terminal_policy_action(events))
        evidence = evaluate_agent_history("Inspecte le projet", events)
        self.assertEqual(evidence.failure_code, "prohibited_terminal_action")

    def test_final_summary_rejects_tool_payloads_and_future_actions(self) -> None:
        """Keep final browser text factual and free of pending work or raw calls."""

        project = [
            action("terminal", "pwd", {"command": "pwd"}, 1),
            observation("terminal", "pwd", 2),
        ]
        unsafe = evaluate_agent_history(
            "Inspecte", [*project, *finish('<tool_call>{"name":"terminal"}', 3)]
        )
        future = evaluate_agent_history(
            "Inspecte", [*project, *finish("Je vais maintenant corriger le fichier.", 3)]
        )
        self.assertEqual(unsafe.failure_code, "unsafe_final_summary")
        self.assertEqual(future.failure_code, "future_action_in_final_summary")

    def test_successful_noop_replacement_is_detected(self) -> None:
        """Stop a byte-identical replacement even if the editor reports success."""

        events = replacement("noop", 1, "same", "same")
        self.assertTrue(has_successful_noop_file_editor_replacement(events))

    def test_repeated_hook_denials_are_correlated_to_exact_replacements(self) -> None:
        """Detect identical denied payloads without interpreting their content."""

        events: list[dict[str, object]] = []
        for offset, call_id in ((1, "one"), (3, "two")):
            events.extend(
                [
                    action(
                        "file_editor",
                        call_id,
                        {
                            "command": "str_replace",
                            "path": "/workspace/source.py",
                            "old_str": "old",
                            "new_str": "new",
                        },
                        offset,
                    ),
                    hook("file_editor", call_id, offset + 1),
                ]
            )
        self.assertTrue(has_repeated_hook_blocked_file_editor_replacement(events))

    def test_repeated_immutable_test_writes_are_detected(self) -> None:
        """Stop two authenticated test-write attempts without source progress."""

        events: list[dict[str, object]] = []
        for offset, call_id in ((1, "one"), (3, "two")):
            events.extend(
                [
                    action(
                        "file_editor",
                        call_id,
                        {
                            "command": "str_replace",
                            "path": "/workspace/tests/test_source.py",
                            "old_str": "a",
                            "new_str": "b",
                        },
                        offset,
                    ),
                    hook(
                        "file_editor",
                        call_id,
                        offset + 1,
                        reason=IMMUTABLE_TEST_REASON,
                    ),
                ]
            )
        self.assertTrue(has_repeated_hook_blocked_immutable_test_edit(events))

    def test_repeated_failed_reads_and_exact_replacements_are_detected(self) -> None:
        """Stop repeated native failures that cannot reveal a new source state."""

        views: list[dict[str, object]] = []
        edits: list[dict[str, object]] = []
        for offset, call_id in ((1, "one"), (3, "two")):
            views.extend(
                [
                    action(
                        "file_editor",
                        f"view-{call_id}",
                        {"command": "view", "path": "/workspace/missing.py"},
                        offset,
                    ),
                    observation(
                        "file_editor", f"view-{call_id}", offset + 1, is_error=True
                    ),
                ]
            )
            failed_edit = replacement(call_id, offset, "missing", "fixed")
            failed_edit[1] = observation(
                "file_editor", call_id, offset + 1, is_error=True
            )
            edits.extend(failed_edit)
        self.assertTrue(has_repeated_failed_file_editor_view(views))
        self.assertTrue(has_repeated_failed_file_editor_replacement(edits))

    def test_read_cycles_and_sweeps_are_detected_generically(self) -> None:
        """Detect repeated reads by shape and count, independent of file names."""

        alternating: list[dict[str, object]] = []
        for index, path in enumerate(("a", "b", "a", "b", "a", "b"), start=1):
            call_id = f"read-{index}"
            alternating.extend(
                [
                    action(
                        "file_editor",
                        call_id,
                        {"command": "view", "path": f"/workspace/{path}.py"},
                        index * 2 - 1,
                    ),
                    observation("file_editor", call_id, index * 2),
                ]
            )
        self.assertTrue(has_repeated_successful_file_editor_view_cycle(alternating))

        sweep: list[dict[str, object]] = []
        for index in range(1, 11):
            call_id = f"sweep-{index}"
            path = "a.py" if index % 2 else "b.py"
            sweep.extend(
                [
                    action(
                        "file_editor",
                        call_id,
                        {"command": "view", "path": f"/workspace/{path}"},
                        index * 2 - 1,
                    ),
                    observation("file_editor", call_id, index * 2),
                ]
            )
        self.assertTrue(has_repeated_successful_file_editor_read_sweep(sweep))

    def test_successful_expansion_and_reversal_cycles_are_detected(self) -> None:
        """Recognize generic successful edit cycles without project-specific rules."""

        expansion = [
            *replacement("one", 1, "x", "xx"),
            *replacement("two", 3, "x", "xx"),
            *replacement("three", 5, "x", "xx"),
        ]
        reversal = [
            *replacement("one", 1, "a", "b"),
            *replacement("two", 3, "b", "a"),
            *replacement("three", 5, "a", "b"),
        ]
        self.assertTrue(has_repeated_successful_file_editor_expansion_cycle(expansion))
        self.assertTrue(has_repeated_successful_file_editor_replacement_cycle(reversal))

    def test_failed_edit_reread_cycle_is_detected_after_three_rounds(self) -> None:
        """Stop repeated failed edit rounds even when each round includes a reread."""

        events: list[dict[str, object]] = []
        index = 1
        for round_number in range(3):
            for attempt in range(2):
                call_id = f"edit-{round_number}-{attempt}"
                failed = replacement(call_id, index, f"old-{attempt}", "new")
                failed[1] = observation(
                    "file_editor", call_id, index + 1, is_error=True
                )
                events.extend(failed)
                index += 2
            if round_number < 2:
                call_id = f"read-{round_number}"
                events.extend(
                    [
                        action(
                            "file_editor",
                            call_id,
                            {"command": "view", "path": "/workspace/source.py"},
                            index,
                        ),
                        observation("file_editor", call_id, index + 1),
                    ]
                )
                index += 2
        self.assertTrue(has_repeated_failed_file_editor_retry_cycle(events))

    def test_public_failures_do_not_echo_private_values(self) -> None:
        """Return a fixed browser-safe fallback for unknown internal codes."""

        self.assertEqual(
            public_failure_summary("private secret path"),
            "Le run OpenHands n'a pas abouti.",
        )


if __name__ == "__main__":
    unittest.main()

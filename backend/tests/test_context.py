from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.database import Database  # noqa: E402
from app.main import (  # noqa: E402
    CONTEXT_INPUT_TOKEN_BUDGET,
    CONTEXT_WINDOW_TOKEN_LIMIT,
    FINAL_RESPONSE_TOKEN_LIMIT,
    MAX_USER_MESSAGE_BYTES,
    SYSTEM_AND_TEMPLATE_TOKEN_RESERVE,
    build_model_messages,
    estimate_content_tokens,
    remove_thinking,
    select_history_for_context,
)


def pair(index: int, size: int) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": f"u{index}-" + "u" * size},
        {"role": "assistant", "content": f"a{index}-" + "a" * size},
    ]


class ContextBudgetTests(unittest.TestCase):
    def test_final_budget_matches_the_active_8192_context_without_reasoning_reserve(self) -> None:
        self.assertEqual(CONTEXT_WINDOW_TOKEN_LIMIT, 8192)
        self.assertEqual(
            CONTEXT_INPUT_TOKEN_BUDGET,
            CONTEXT_WINDOW_TOKEN_LIMIT
            - FINAL_RESPONSE_TOKEN_LIMIT
            - SYSTEM_AND_TEMPLATE_TOKEN_RESERVE,
        )
        self.assertEqual(CONTEXT_INPUT_TOKEN_BUDGET, 6656)

    def test_short_history_is_preserved_in_chronological_complete_pairs(self) -> None:
        history = pair(1, 20) + pair(2, 20)
        self.assertEqual(select_history_for_context(history, "question"), history)

    def test_history_exactly_under_limit_is_preserved(self) -> None:
        question = "q" * 100
        remaining = CONTEXT_INPUT_TOKEN_BUDGET - estimate_content_tokens(question)
        content_size = remaining // 2 - 8
        history = [
            {"role": "user", "content": "u" * content_size},
            {"role": "assistant", "content": "a" * content_size},
        ]
        retained = select_history_for_context(history, question)
        total = estimate_content_tokens(question) + sum(
            estimate_content_tokens(message["content"]) for message in retained
        )
        self.assertEqual(retained, history)
        self.assertLessEqual(total, CONTEXT_INPUT_TOKEN_BUDGET)

    def test_slight_overflow_removes_the_oldest_pair_only(self) -> None:
        old_pair = pair(1, 2800)
        recent_pair = pair(2, 600)
        history = old_pair + recent_pair
        retained = select_history_for_context(history, "question récente")
        self.assertEqual(retained, recent_pair)

    def test_very_long_history_keeps_a_recent_complete_suffix(self) -> None:
        history = [message for index in range(30) for message in pair(index, 180)]
        retained = select_history_for_context(history, "question actuelle")
        self.assertLess(len(retained), len(history))
        self.assertEqual(len(retained) % 2, 0)
        self.assertEqual(retained[-2:], history[-2:])
        self.assertEqual(
            [message["role"] for message in retained],
            ["user", "assistant"] * (len(retained) // 2),
        )
        total = estimate_content_tokens("question actuelle") + sum(
            estimate_content_tokens(message["content"]) for message in retained
        )
        self.assertLessEqual(total, CONTEXT_INPUT_TOKEN_BUDGET)

    def test_current_question_is_always_last_and_internal_no_think_does_not_mutate_it(self) -> None:
        history = pair(1, 100)
        question = "Texte original"
        messages = build_model_messages(history, question)
        self.assertEqual(question, "Texte original")
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "Texte original\n/no_think")
        self.assertNotIn("/no_think", history[-1]["content"])

    def test_question_alone_too_large_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            select_history_for_context([], "q" * (CONTEXT_INPUT_TOKEN_BUDGET + 1))
        self.assertLessEqual(
            estimate_content_tokens("q" * MAX_USER_MESSAGE_BYTES),
            CONTEXT_INPUT_TOKEN_BUDGET,
        )

    def test_context_reduction_never_deletes_old_messages_from_sqlite(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-context-test-", dir=Path(__file__).resolve().parent
        )
        try:
            database = Database(Path(temporary_directory.name) / "context.sqlite3")
            database.initialize()
            conversation_id, user_id = database.create_pending_conversation("u0-" + "u" * 200)
            database.complete_generation(conversation_id, user_id, "a0-" + "a" * 200)
            for index in range(1, 20):
                revision = database.get_conversation(conversation_id)["revision"]
                user_id = database.add_pending_message(
                    conversation_id, f"u{index}-" + "u" * 200, revision
                )
                database.complete_generation(
                    conversation_id, user_id, f"a{index}-" + "a" * 200
                )

            detail = database.get_conversation(conversation_id)
            stored_history = [
                {"role": message["role"], "content": message["content"]}
                for message in detail["messages"]
            ]
            retained = select_history_for_context(stored_history, "question finale")
            self.assertLess(len(retained), len(stored_history))
            self.assertEqual(database.count_messages(conversation_id), 40)
        finally:
            temporary_directory.cleanup()


class ThinkingFilterTests(unittest.TestCase):
    def test_filter_handles_multiple_case_and_spacing_variants(self) -> None:
        content = (
            "< THINK >secret 1< / THINK >Réponse "
            "[ Start Thinking ]secret 2[ End Thinking ]finale"
        )
        self.assertEqual(remove_thinking(content), "Réponse finale")

    def test_filter_handles_incomplete_opening_and_isolated_closing_markers(self) -> None:
        self.assertEqual(remove_thinking("Réponse</think> finale"), "Réponse finale")
        self.assertEqual(remove_thinking("Réponse [ End Thinking ] finale"), "Réponse  finale")
        self.assertEqual(remove_thinking("Réponse<think>secret inachevé"), "Réponse")
        self.assertEqual(remove_thinking("<think>secret"), "")

    def test_filter_handles_nested_and_mixed_markers_without_leaking(self) -> None:
        self.assertEqual(
            remove_thinking(
                "<think>outer <think>inner</think> secret</think>final"
            ),
            "final",
        )
        self.assertEqual(
            remove_thinking(
                "[Start Thinking]outer [Start Thinking]inner"
                "[End Thinking] secret[End Thinking]final"
            ),
            "final",
        )
        self.assertEqual(
            remove_thinking(
                "<think>outer [Start Thinking]inner"
                "[End Thinking] secret</think>final"
            ),
            "final",
        )
        self.assertEqual(
            remove_thinking(
                "Visible<think>outer [Start Thinking]inner"
                "</think> texte suspect[End Thinking]fin suspecte"
            ),
            "Visible",
        )


if __name__ == "__main__":
    unittest.main()

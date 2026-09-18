"""Tests for the development prompt suffix used by the OpenHands runner."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.model_registry import load_model_registry  # noqa: E402
from app.openhands_prompt import (  # noqa: E402
    build_openhands_agent_context,
    development_openhands_suffix,
)


class OpenHandsPromptTests(unittest.TestCase):
    """Keep one central generic prompt contract for browser and agent."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the same registry source that serves browser profiles."""

        cls.registry = load_model_registry(project_root=PROJECT_DIRECTORY)

    def test_suffix_reuses_the_development_profile_prompt(self) -> None:
        """Prevent a divergent copy of the central development prompt."""

        self.assertEqual(
            development_openhands_suffix(self.registry),
            self.registry.system_prompt("development", include_memory=False),
        )

    def test_official_context_preserves_the_native_openhands_prompt(self) -> None:
        """Supply a suffix and disable untrusted project or public skills."""

        captured: dict[str, object] = {}

        def factory(**kwargs: object) -> dict[str, object]:
            """Capture the exact AgentContext keyword contract."""

            captured.update(kwargs)
            return captured

        result = build_openhands_agent_context(self.registry, factory)
        self.assertIs(result, captured)
        self.assertEqual(
            captured["system_message_suffix"],
            development_openhands_suffix(self.registry),
        )
        self.assertNotIn("system_prompt", captured)
        self.assertEqual(
            {key: captured[key] for key in captured if key.startswith("load_")},
            {
                "load_user_skills": False,
                "load_public_skills": False,
                "load_project_skills": False,
                "load_memory": False,
            },
        )

    def test_development_prompt_is_generic_and_test_safe(self) -> None:
        """Require reusable editor guidance without a benchmark-specific answer."""

        suffix = development_openhands_suffix(self.registry)
        self.assertIn("spécifications lisibles mais immuables", suffix)
        self.assertIn("recopie `old_str` exactement", suffix)
        self.assertIn("relis l'état courant", suffix)
        self.assertIn("sans accès réseau", suffix)
        self.assertIn("FinishTool", suffix)
        self.assertNotIn("inventory/models.py", suffix)
        self.assertNotIn("test_rejects_bool_as_numeric_value", suffix)
        self.assertNotIn("sed -i", suffix)


if __name__ == "__main__":
    unittest.main()

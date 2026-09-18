from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = PROJECT_ROOT / "tools" / "openhands" / "development_runtime.py"


def load_runtime_module():
    """Load the standalone managed-runtime helper without starting a process."""

    module_name = "lea_development_runtime_tests"
    specification = importlib.util.spec_from_file_location(module_name, RUNTIME_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError("Le helper Programmation ne peut pas être chargé pour les tests.")
    module = importlib.util.module_from_spec(specification)
    sys.modules[module_name] = module
    specification.loader.exec_module(module)
    return module


class DevelopmentRuntimeStateTests(unittest.TestCase):
    """Protect stale-state recovery without weakening process ownership checks."""

    def setUp(self) -> None:
        """Redirect the helper's ignored state file to an isolated temporary directory."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.runtime = load_runtime_module()
        self.runtime.STATE_PATH = Path(self.temporary_directory.name) / "development-runtime.json"
        self.runtime.LOG_DIRECTORY = Path(self.temporary_directory.name)
        self.configuration = {"port": 8081}

    def test_stop_marks_a_dead_owned_record_stopped_when_the_port_is_free(self) -> None:
        """A dead PID plus an unused port is safe stale evidence, not an ambiguous process."""

        self.runtime.write_state(
            {
                "schema_version": 1,
                "phase": "ready",
                "process": {"pid": 9876, "executable": "C:\\owned\\llama-server.exe", "created_filetime": 1},
            }
        )
        with (
            patch.object(self.runtime, "process_identity", return_value=None),
            patch.object(self.runtime, "listener_pids", return_value=set()),
        ):
            result = self.runtime.stop(self.configuration)

        self.assertEqual(result, {"state": "stopped", "profile_id": None})
        self.assertEqual(self.runtime.read_state()["phase"], "stopped")

    def test_a_surviving_pid_remains_ambiguous_even_when_the_port_is_free(self) -> None:
        """The helper never clears a record while any process still owns its recorded PID."""

        state = {"process": {"pid": 9876, "executable": "C:\\owned\\llama-server.exe", "created_filetime": 1}}
        with (
            patch.object(self.runtime, "process_identity", return_value={"pid": 9876}),
            patch.object(self.runtime, "listener_pids", return_value=set()),
        ):
            self.assertFalse(self.runtime.state_is_conclusively_stale(state, self.configuration))


class DevelopmentRuntimeArgumentTests(unittest.TestCase):
    """Keep llama.cpp's custom-template ordering compatible with native tools."""

    def setUp(self) -> None:
        """Load the helper once per test without inspecting or starting a real model."""

        self.runtime = load_runtime_module()

    def test_jinja_precedes_the_custom_template_file(self) -> None:
        """A custom template must follow --jinja for llama.cpp to enable its full Jinja path."""

        configuration = {
            "model_path": Path("L:/models/development.gguf"),
            "host": "127.0.0.1",
            "port": 8081,
            "alias": "lea-development-openhands",
            "context": 22000,
            "template": Path("L:/templates/qwen2.5-coder.jinja"),
            "runtime": {
                "parallel_slots": 1,
                "cache_type_k": "q4_0",
                "cache_type_v": "q4_0",
                "cache_ram": False,
                "gpu_layers": "auto",
                "fit": True,
                "fit_target_mib": 1024,
                "fit_context_min_tokens": 22000,
                "priority": -1,
                "threads": 8,
                "batch_size": 512,
                "ubatch_size": 128,
                "mmap": True,
                "jinja": True,
                "skip_chat_parsing": False,
            },
        }

        arguments = self.runtime.runtime_arguments(configuration)

        self.assertLess(arguments.index("--jinja"), arguments.index("--chat-template-file"))
        self.assertEqual(arguments[arguments.index("--chat-template-file") + 1], str(configuration["template"]))
        self.assertIn("--no-skip-chat-parsing", arguments)


if __name__ == "__main__":
    unittest.main()

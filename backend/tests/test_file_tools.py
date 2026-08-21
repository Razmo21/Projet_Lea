from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from pydantic import ValidationError


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.database import Database, ProjectNotFoundError  # noqa: E402
from app.file_tools import (  # noqa: E402
    MAX_TEXT_FILE_BYTES,
    TOOL_ARGUMENT_MODELS,
    FileToolError,
    FileToolExecutor,
)
from app.workspace import WorkspaceGuard  # noqa: E402


class FileToolExecutorTests(unittest.TestCase):
    """Exerce chaque outil sur un projet temporaire sans commande système."""

    def setUp(self) -> None:
        """Crée un projet, une base et un stockage de checkpoints isolés."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-file-tools-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.workspace = self.base / "IA_WORKSPACE"
        self.project = self.workspace / "Projet Ω"
        (self.project / "src").mkdir(parents=True)
        (self.project / "node_modules").mkdir()
        (self.project / "models").mkdir()
        (self.project / "src" / "app.py").write_text(
            "alpha = 1\nprint(alpha)\n", encoding="utf-8", newline="\n"
        )
        (self.project / "bom.txt").write_text("début\n", encoding="utf-8-sig")
        (self.project / "utf16.txt").write_text("ligne Ω\n", encoding="utf-16")
        (self.project / "binary.bin").write_bytes(b"\x00\x01\x02")
        (self.project / "ignored.txt").write_text("secret alpha", encoding="utf-8")
        (self.project / "skip.tmp").write_text("secret alpha", encoding="utf-8")
        (self.project / "keep.tmp").write_text("visible alpha", encoding="utf-8")
        (self.project / "node_modules" / "secret.js").write_text("alpha", encoding="utf-8")
        (self.project / "models" / "weight.gguf").write_bytes(b"model")
        (self.project / ".gitignore").write_text(
            "ignored.txt\n*.tmp\n!keep.tmp\n", encoding="utf-8"
        )
        (self.project / ".leaignore").write_text("*.note\n", encoding="utf-8")
        (self.project / "private.note").write_text("alpha", encoding="utf-8")
        self.database = Database(self.base / "lea.sqlite3")
        self.database.initialize()
        projects = self.database.sync_projects([("Projet Ω", "Projet Ω")])
        self.project_id = projects[0]["id"]
        self.guard = WorkspaceGuard(self.workspace)
        self.executor = FileToolExecutor(
            self.database,
            self.guard,
            self.base / "checkpoints",
        )

    def tearDown(self) -> None:
        """Supprime tous les fichiers et checkpoints créés par chaque test."""

        self.temporary_directory.cleanup()

    def activate(self) -> None:
        """Sélectionne le projet temporaire par le même registre que l'API."""

        self.database.activate_project(self.project_id)

    def test_active_project_and_strict_typed_arguments_are_required(self) -> None:
        """Aucun outil ne fonctionne sans sélection ou avec un argument inconnu."""

        with self.assertRaises(ProjectNotFoundError):
            self.executor.execute("list_files", {})
        self.activate()
        with self.assertRaises(ValidationError):
            self.executor.execute("read_file", {"path": "src/app.py", "extra": True})
        with self.assertRaises(FileToolError):
            self.executor.execute("unknown", {})
        self.assertEqual(set(TOOL_ARGUMENT_MODELS), {
            "list_files", "search_files", "read_file", "read_file_range",
            "create_file", "apply_patch", "move_file", "rename_file",
            "delete_file", "make_directory", "file_info",
        })
        self.assertEqual(
            {schema["function"]["name"] for schema in self.executor.schemas()},
            set(TOOL_ARGUMENT_MODELS),
        )

    def test_list_and_search_are_paginated_and_respect_ignore_files(self) -> None:
        """Les sorties restent bornées et n'incluent aucun dossier ou motif ignoré."""

        self.activate()
        first = self.executor.execute("list_files", {"limit": 2})
        self.assertEqual(len(first["entries"]), 2)
        self.assertIsNotNone(first["next_cursor"])
        all_entries: list[dict[str, object]] = []
        cursor = 0
        while cursor is not None:
            page = self.executor.execute("list_files", {"limit": 2, "cursor": cursor})
            all_entries.extend(page["entries"])
            cursor = page["next_cursor"]
        paths = {entry["path"] for entry in all_entries}
        self.assertIn("keep.tmp", paths)
        self.assertIn("src/app.py", paths)
        self.assertNotIn("ignored.txt", paths)
        self.assertNotIn("skip.tmp", paths)
        self.assertFalse(any(path.startswith("node_modules") for path in paths))
        self.assertFalse(any(path.startswith("models") for path in paths))

        matches = self.executor.execute("search_files", {"query": "ALPHA", "limit": 1})
        self.assertEqual(len(matches["matches"]), 1)
        self.assertIsNotNone(matches["next_cursor"])
        second = self.executor.execute(
            "search_files",
            {"query": "alpha", "limit": 10, "cursor": matches["next_cursor"]},
        )
        matched_paths = {item["path"] for item in matches["matches"] + second["matches"]}
        self.assertEqual(matched_paths, {"keep.tmp", "src/app.py"})

    def test_reads_preserve_unicode_encodings_and_reject_binary_or_oversize(self) -> None:
        """Les lectures exposent hash/encodage et refusent les formats non pris en charge."""

        self.activate()
        utf8_bom = self.executor.execute("read_file", {"path": "bom.txt"})
        self.assertEqual(utf8_bom["encoding"], "utf-8-sig")
        utf16 = self.executor.execute("read_file", {"path": "utf16.txt"})
        self.assertEqual(utf16["encoding"], "utf-16-le")
        self.executor.execute(
            "apply_patch",
            {
                "path": "bom.txt",
                "expected_sha256": utf8_bom["sha256"],
                "old_text": "début",
                "new_text": "fin",
            },
        )
        self.executor.execute(
            "apply_patch",
            {
                "path": "utf16.txt",
                "expected_sha256": utf16["sha256"],
                "old_text": "ligne Ω",
                "new_text": "ligne finale",
            },
        )
        self.assertTrue((self.project / "bom.txt").read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertTrue((self.project / "utf16.txt").read_bytes().startswith(b"\xff\xfe"))
        self.assertIn("ligne finale", (self.project / "utf16.txt").read_text(encoding="utf-16"))
        ranged = self.executor.execute(
            "read_file_range",
            {"path": "src/app.py", "start_line": 2, "end_line": 2},
        )
        self.assertEqual(ranged["content"], "print(alpha)\n")
        with self.assertRaises(FileToolError):
            self.executor.execute("read_file", {"path": "binary.bin"})
        (self.project / "too-large.txt").write_bytes(b"x" * (MAX_TEXT_FILE_BYTES + 1))
        with self.assertRaises(FileToolError):
            self.executor.execute("read_file", {"path": "too-large.txt"})
        self.assertEqual(
            self.executor.execute("search_files", {"path": "ignored.txt", "query": "alpha"})["matches"],
            [],
        )

    def test_create_patch_stale_hash_and_toctou_are_safe_and_checkpointed(self) -> None:
        """Une écriture est atomique, versionnée et refuse tout changement extérieur."""

        self.activate()
        run_id = str(uuid.uuid4())
        created = self.executor.execute(
            "create_file",
            {"path": "src/new.txt", "content": "avant\n"},
            run_id=run_id,
        )
        self.assertEqual((self.project / "src" / "new.txt").read_text(encoding="utf-8"), "avant\n")
        with self.assertRaises((FileToolError, OSError)):
            self.executor.execute(
                "create_file",
                {"path": "src/new.txt", "content": "écrasement"},
                run_id=run_id,
            )

        patched = self.executor.execute(
            "apply_patch",
            {
                "path": "src/new.txt",
                "expected_sha256": created["sha256"],
                "old_text": "avant",
                "new_text": "après",
            },
            run_id=run_id,
        )
        self.assertEqual((self.project / "src" / "new.txt").read_text(encoding="utf-8"), "après\n")
        with self.assertRaisesRegex(FileToolError, "changé"):
            self.executor.execute(
                "apply_patch",
                {
                    "path": "src/new.txt",
                    "expected_sha256": created["sha256"],
                    "old_text": "après",
                    "new_text": "interdit",
                },
                run_id=run_id,
            )

        original_prepare = self.executor.checkpoints.prepare

        def tampering_prepare(*args, **kwargs):
            """Simule une écriture extérieure après le checkpoint, avant le replace."""

            checkpoint = original_prepare(*args, **kwargs)
            (self.project / "src" / "new.txt").write_text("extérieur\n", encoding="utf-8")
            return checkpoint

        self.executor.checkpoints.prepare = tampering_prepare
        with self.assertRaisesRegex(FileToolError, "pendant le patch"):
            self.executor.execute(
                "apply_patch",
                {
                    "path": "src/new.txt",
                    "expected_sha256": patched["sha256"],
                    "old_text": "après",
                    "new_text": "jamais",
                },
                run_id=run_id,
            )
        self.assertEqual((self.project / "src" / "new.txt").read_text(encoding="utf-8"), "extérieur\n")
        manifest = json.loads(
            (self.base / "checkpoints" / run_id / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual([entry["order"] for entry in manifest], list(range(1, len(manifest) + 1)))
        self.assertEqual(manifest[0]["status"], "completed")
        self.assertTrue((self.base / "checkpoints" / run_id / manifest[1]["changes"][0]["backup"]).is_file())

    def test_directory_move_rename_delete_and_path_escapes(self) -> None:
        """Toutes les mutations sauvegardent l'original et n'écrasent aucune cible."""

        self.activate()
        run_id = str(uuid.uuid4())
        self.executor.execute("make_directory", {"path": "generated"}, run_id=run_id)
        created = self.executor.execute(
            "create_file",
            {"path": "generated/a.txt", "content": "contenu"},
            run_id=run_id,
        )
        moved = self.executor.execute(
            "move_file",
            {
                "source": "generated/a.txt",
                "destination": "generated/b.txt",
                "expected_sha256": created["sha256"],
            },
            run_id=run_id,
        )
        renamed = self.executor.execute(
            "rename_file",
            {
                "path": "generated/b.txt",
                "new_name": "c.txt",
                "expected_sha256": moved["sha256"],
            },
            run_id=run_id,
        )
        info = self.executor.execute("file_info", {"path": "generated/c.txt"})
        self.assertEqual(info["sha256"], renamed["sha256"])
        self.executor.execute(
            "delete_file",
            {"path": "generated/c.txt", "expected_sha256": renamed["sha256"]},
            run_id=run_id,
        )
        self.assertFalse((self.project / "generated" / "c.txt").exists())

        for unsafe in ("..\\outside.txt", "C:\\outside.txt", "\\\\server\\share\\x"):
            with self.subTest(path=unsafe), self.assertRaises((FileToolError, ValueError)):
                self.executor.execute(
                    "create_file",
                    {"path": unsafe, "content": "interdit"},
                    run_id=run_id,
                )


if __name__ == "__main__":
    unittest.main()

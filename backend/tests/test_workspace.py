from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.workspace import WorkspaceGuard, WorkspacePathError  # noqa: E402
from app.main import create_app  # noqa: E402


class WorkspaceGuardTests(unittest.TestCase):
    """Vérifie le confinement Windows avant l'ajout des outils de fichiers."""

    def setUp(self) -> None:
        """Crée une fausse racine de workspace entièrement isolée sous le dépôt."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-workspace-test-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.root = self.base / "IA_WORKSPACE"
        self.root.mkdir()
        (self.root / "Alpha").mkdir()
        (self.root / "Été_项目").mkdir()
        (self.root / ("long_" + "x" * 120)).mkdir()
        self.guard = WorkspaceGuard(self.root)

    def tearDown(self) -> None:
        """Libère les dossiers de test, y compris toute junction déjà détachée."""

        self.temporary_directory.cleanup()

    def test_real_unicode_long_and_case_variant_projects_are_accepted(self) -> None:
        """Les noms légitimes restent utilisables sans comparaison sensible à la casse."""

        alpha = self.guard.resolve_project("ALPHA")
        self.assertEqual(alpha.identity, self.guard.resolve_project("Alpha").identity)
        self.assertTrue(self.guard.resolve_project("Été_项目").path.is_dir())
        long_name = "long_" + "x" * 120
        self.assertEqual(self.guard.resolve_project(long_name).path.name, long_name)
        self.assertEqual(
            [project.name for project in self.guard.discover_projects()],
            ["Alpha", long_name, "Été_项目"],
        )

    def test_traversal_absolute_unc_other_drive_nested_and_missing_are_rejected(self) -> None:
        """Aucune variante syntaxique ne peut désigner autre chose qu'un enfant direct réel."""

        invalid = (
            "..",
            "..\\outside",
            str(self.root / "Alpha"),
            "C:\\Windows",
            "\\\\server\\share",
            "Alpha\\nested",
            "missing",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(WorkspacePathError):
                self.guard.resolve_project(value)

    @unittest.skipUnless(os.name == "nt", "Les junctions sont spécifiques à Windows.")
    def test_junction_is_rejected_even_when_it_targets_an_existing_directory(self) -> None:
        """Un reparse point n'est jamais adopté comme projet, même s'il semble local."""

        outside = self.base / "outside"
        outside.mkdir()
        junction = self.root / "junction"
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest(f"Création de junction indisponible : {result.stderr}")
        with self.assertRaises(WorkspacePathError):
            self.guard.resolve_project("junction")
        self.assertNotIn("junction", [project.name for project in self.guard.discover_projects()])

    def test_revalidation_detects_a_toctou_directory_replacement(self) -> None:
        """Un dossier échangé après validation est refusé avant l'opération suivante."""

        validated = self.guard.resolve_project("Alpha")
        original = self.root / "Alpha"
        moved = self.root / "Alpha_original"
        original.rename(moved)
        original.mkdir()
        with self.assertRaisesRegex(WorkspacePathError, "changé"):
            self.guard.revalidate_project(validated)


class ProjectApiTests(unittest.TestCase):
    """Vérifie l'actualisation et la sélection sans exposer la racine absolue."""

    def setUp(self) -> None:
        """Démarre l'API sur une base et un workspace temporaires."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-project-api-", dir=Path(__file__).resolve().parent
        )
        self.base = Path(self.temporary_directory.name)
        self.root = self.base / "IA_WORKSPACE"
        self.root.mkdir()
        (self.root / "Projet Ω").mkdir()
        application = create_app(
            database_path=self.base / "projects.sqlite3",
            model_gateway=object(),
            workspace_root=self.root,
        )
        self.client_context = TestClient(application)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        """Ferme le lifespan FastAPI avant de supprimer les fichiers temporaires."""

        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def test_refresh_activate_empty_and_origin_protection(self) -> None:
        """Le navigateur manipule des UUID fixes, jamais un chemin fourni librement."""

        catalog = self.client.get("/api/projects").json()
        self.assertEqual([project["name"] for project in catalog["projects"]], ["Projet Ω"])
        self.assertNotIn(str(self.root), str(catalog))
        project_id = catalog["projects"][0]["id"]

        selected = self.client.post(
            f"/api/projects/{project_id}/activate",
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["active_project_id"], project_id)

        refused = self.client.post(
            "/api/projects/refresh",
            headers={"Origin": "https://example.com"},
        )
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/projects/not-a-uuid/activate",
                headers={"Origin": "http://127.0.0.1:5173"},
            ).status_code,
            404,
        )

        (self.root / "Projet Ω").rmdir()
        refreshed = self.client.post(
            "/api/projects/refresh",
            headers={"Origin": "http://127.0.0.1:5173"},
        ).json()
        self.assertEqual(refreshed, {"projects": [], "active_project_id": None})


if __name__ == "__main__":
    unittest.main()

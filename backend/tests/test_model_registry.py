from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
PROJECT_DIRECTORY = BACKEND_DIRECTORY.parent
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.main import HttpModelGateway, build_model_messages, create_app  # noqa: E402
from app.model_registry import RegistryError, load_model_registry  # noqa: E402


class ModelRegistryTests(unittest.TestCase):
    """Vérifie la source de vérité commune sans démarrer de modèle."""

    def setUp(self) -> None:
        """Crée une racine miniature contenant tous les fichiers exigés."""

        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-registry-test-", dir=Path(__file__).resolve().parent
        )
        self.root = Path(self.temporary_directory.name)
        self.document = json.loads(
            (PROJECT_DIRECTORY / "config" / "models.json").read_text(encoding="utf-8")
        )
        for relative_path in (
            "runtime/llama.cpp/llama-server.exe",
            self.document["profiles"][0]["model_path"],
            self.document["profiles"][1]["model_path"],
        ):
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test")
        for prompt_name in ("reliability.md", "general.md", "development.md", "memory.md"):
            path = self.root / "config" / "prompts" / prompt_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"prompt {prompt_name}", encoding="utf-8")

    def tearDown(self) -> None:
        """Supprime la racine miniature après chaque validation."""

        self.temporary_directory.cleanup()

    def load(self, document: dict | None = None):
        """Écrit une variante JSON puis appelle le même chargeur que FastAPI."""

        registry_path = self.root / "config" / "models.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(document or self.document, ensure_ascii=False),
            encoding="utf-8",
        )
        return load_model_registry(registry_path, project_root=self.root)

    def run_temporary_launcher(self, document: dict) -> subprocess.CompletedProcess[str]:
        """Exécute `status` dans une racine minimale pour tester le parseur PowerShell."""

        registry_path = self.root / "config" / "models.json"
        registry_path.write_text(json.dumps(document), encoding="utf-8")
        launcher_path = self.root / "lea.ps1"
        launcher_path.write_text(
            (PROJECT_DIRECTORY / "lea.ps1").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return subprocess.run(
            (
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(launcher_path),
                "status",
                "-Json",
            ),
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )

    def test_real_registry_exposes_two_profiles_without_sensitive_paths(self) -> None:
        """Le registre réel conserve Général par défaut et masque chemins/hash à l’API."""

        registry = load_model_registry()

        self.assertEqual(registry.document.default_profile_id, "general")
        self.assertEqual([profile.id for profile in registry.document.profiles], ["general", "development"])
        self.assertEqual(registry.profile("general").context_tokens, 8192)
        self.assertEqual(registry.profile("development").context_tokens, 16000)
        self.assertEqual(registry.profile("development").runtime.gpu_layers, "auto")
        self.assertFalse(registry.profile("development").runtime.mmap)
        self.assertEqual(registry.profile("development").runtime.cache_type_k, "q4_0")
        self.assertEqual(registry.profile("development").runtime.fit_context_min_tokens, 16000)
        self.assertIn("CONTRAT COMMUN DE FIABILITÉ", registry.system_prompt("general"))
        development_prompt = registry.system_prompt("development")
        self.assertIn("CONTRAT COMMUN DE FIABILITÉ", development_prompt)
        self.assertIn(
            "Cette demande ne relève pas du profil Programmation. Passe au profil Général.",
            development_prompt,
        )
        self.assertIn("N’invente jamais un fichier non lu", development_prompt)
        self.assertIn("Ne révèle pas de raisonnement interne", development_prompt)
        public = registry.public_profiles()
        self.assertEqual([profile["id"] for profile in public], ["general", "development"])
        self.assertNotIn("model_path", public[0])
        self.assertNotIn("expected_sha256", public[0])

    def test_invalid_ids_names_hashes_and_types_are_rejected(self) -> None:
        """Les identités et types ambigus échouent avant tout lancement."""

        mutations = (
            (lambda data: data["profiles"][1].__setitem__("id", "general"), "uniques"),
            (lambda data: data["profiles"][0].__setitem__("display_name", " "), "vide"),
            (lambda data: data["profiles"][0].__setitem__("expected_sha256", "bad"), "SHA-256"),
            (lambda data: data["profiles"][0].__setitem__("model_type", "unknown"), "Type de modèle"),
        )
        for mutate, expected in mutations:
            with self.subTest(expected=expected):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaisesRegex(RegistryError, expected):
                    self.load(data)

    def test_required_profiles_and_resource_thread_limit_are_rejected(self) -> None:
        """Le registre conserve les deux profils de base et leurs limites CPU centrales."""

        mutations = (
            (lambda data: data["profiles"].pop(), "Profils obligatoires absents"),
            (
                lambda data: data["profiles"][1]["runtime"].__setitem__("threads", 9),
                "dépasse le nombre de threads",
            ),
        )
        for mutate, expected in mutations:
            with self.subTest(expected=expected):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaisesRegex(RegistryError, expected):
                    self.load(data)

    def test_unknown_capability_tool_permission_and_policy_are_rejected(self) -> None:
        """Chaque référence d’un profil doit appartenir à son catalogue central."""

        mutations = (
            (lambda data: data["profiles"][0]["capabilities"].append("unknown"), "Capacités inconnues"),
            (lambda data: data["profiles"][0]["tools"].append("unknown"), "Outils inconnus"),
            (lambda data: data["profiles"][0].__setitem__("workspace_permission", "unknown"), "Permission workspace"),
            (lambda data: data["profiles"][0].__setitem__("resource_policy", "unknown"), "Politique de ressources"),
        )
        for mutate, expected in mutations:
            with self.subTest(expected=expected):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaisesRegex(RegistryError, expected):
                    self.load(data)

    def test_absolute_parent_and_missing_model_paths_are_rejected(self) -> None:
        """Un modèle activé ne peut ni sortir de models ni être absent."""

        invalid_paths = ("C:/Windows/model.gguf", "models/../outside.gguf", "models/missing.gguf")
        for invalid_path in invalid_paths:
            with self.subTest(path=invalid_path):
                data = copy.deepcopy(self.document)
                data["profiles"][0]["model_path"] = invalid_path
                with self.assertRaises(RegistryError):
                    self.load(data)

    def test_disabled_profile_keeps_a_path_confined_to_models(self) -> None:
        """Un profil inactif ne peut pas devenir plus tard une référence extérieure."""

        data = copy.deepcopy(self.document)
        data["profiles"][1]["enabled"] = False
        data["profiles"][1]["model_path"] = "C:/outside.gguf"
        with self.assertRaisesRegex(RegistryError, "chemin relatif|sous"):
            self.load(data)

    def test_incoherent_context_slots_and_resource_thresholds_are_rejected(self) -> None:
        """Les budgets sans entrée et les seuils inversés ne peuvent pas démarrer."""

        mutations = (
            lambda data: data["profiles"][0].__setitem__("context_tokens", 1000),
            lambda data: data["profiles"][0]["runtime"].__setitem__("parallel_slots", 2),
            lambda data: data["profiles"][1]["runtime"].__setitem__("fit_context_min_tokens", 4096),
            lambda data: data["profiles"][1]["runtime"].__setitem__("cache_type_k", "unsafe"),
            lambda data: data["resource_policies"]["general_desktop"].__setitem__(
                "runtime_warning_bytes", 20000000000
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaises(RegistryError):
                    self.load(data)

    def test_models_api_is_driven_by_registry_and_keeps_paths_private(self) -> None:
        """FastAPI expose la liste dynamique sans dupliquer les profils côté frontend."""

        database_path = self.root / "api.sqlite3"
        application = create_app(database_path=database_path)
        with TestClient(application) as client:
            response = client.get("/api/models")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_profile_id"], "general")
        self.assertEqual(payload["active_profile_id"], "general")
        self.assertEqual([profile["id"] for profile in payload["profiles"]], ["general", "development"])
        self.assertNotIn("model_path", json.dumps(payload))
        self.assertNotIn("sha256", json.dumps(payload).lower())

    def test_gateway_and_prompt_use_the_injected_registry(self) -> None:
        """Une application de test ne retombe jamais sur l'endpoint ou prompt global."""

        data = copy.deepcopy(self.document)
        data["runtime"]["port"] = 8181
        registry = self.load(data)
        gateway = HttpModelGateway(registry, "general")
        messages = build_model_messages(
            [],
            "Question de test",
            profile=registry.profile("general"),
            registry=registry,
        )

        self.assertEqual(gateway.url, "http://127.0.0.1:8181/v1/chat/completions")
        self.assertIn("prompt general.md", messages[0]["content"])
        self.assertIn("prompt reliability.md", messages[0]["content"])

    def test_powershell_model_endpoint_is_derived_from_the_registry(self) -> None:
        """Le lanceur réutilise le port et la route modèles centralisés, sans valeur 8080."""

        script = (PROJECT_DIRECTORY / "lea.ps1").read_text(encoding="utf-8")

        self.assertIn("$ModelRuntimePort = [int]$ModelRegistry.runtime.port", script)
        self.assertIn("Port = $ModelRuntimePort", script)
        self.assertIn("Endpoint = $ModelRuntimeModelsEndpoint", script)
        self.assertNotIn("Port = 8080", script)

    def test_powershell_rejects_wrong_json_types_before_status(self) -> None:
        """Le lanceur refuse les chaînes déguisées en port ou booléen avant tout run."""

        invalid_documents = (
            (lambda data: data["runtime"].__setitem__("port", "8080"), "port du runtime"),
            (lambda data: data["profiles"][0].__setitem__("enabled", "false"), "type JSON invalide"),
        )
        for mutate, expected in invalid_documents:
            with self.subTest(expected=expected):
                data = copy.deepcopy(self.document)
                mutate(data)
                completed = self.run_temporary_launcher(data)
                output = f"{completed.stdout}\n{completed.stderr}"
                self.assertNotEqual(completed.returncode, 0, output)
                self.assertIn(expected, output)


if __name__ == "__main__":
    unittest.main()

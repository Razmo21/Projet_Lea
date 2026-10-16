from __future__ import annotations

import copy
import hashlib
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
        # La racine miniature utilise un template factice : son hash doit rester
        # cohérent avec le registre afin de tester les mêmes contrôles que le dépôt.
        self.document["models"][1]["expected_chat_template_sha256"] = hashlib.sha256(
            b"test"
        ).hexdigest()
        self.document["openhands"]["agent_runtime"]["expected_tiktoken_cache_sha256"] = (
            hashlib.sha256(b"test").hexdigest()
        )
        for relative_path in (
            "runtime/llama.cpp/llama-server.exe",
            self.document["models"][0]["model_path"],
            self.document["models"][1]["model_path"],
            self.document["models"][1]["chat_template_path"],
            self.document["openhands"]["agent_runtime"]["tiktoken_cache_path"],
            self.document["openhands"]["sdk_python_path"],
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
            (PROJECT_DIRECTORY / "lea.ps1").read_text(encoding="utf-8").replace(
                "Join-Path $ProjectRoot 'backend\\.venv\\Scripts\\python.exe'",
                "'" + sys.executable.replace("'", "''") + "'",
            ).replace(
                "Join-Path $ProjectRoot 'tools\\model_config.py'",
                "'" + str(PROJECT_DIRECTORY / "tools" / "model_config.py").replace("'", "''") + "'",
            ),
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
        development = registry.profile("development")
        self.assertEqual(
            development.context_tokens,
            self.document["models"][1]["context_tokens"],
        )
        self.assertEqual(development.model_name, "Qwen2.5-Coder-7B-Instruct Q6_K")
        self.assertEqual(development.agent_engine, "OpenHands")
        self.assertEqual(development.orchestrator, "agent_server_sdk")
        self.assertEqual(registry.document.agent_policy.max_actions, 32)
        self.assertEqual(registry.document.agent_policy.max_duration_seconds, 1800)
        self.assertEqual(registry.document.agent_policy.max_action_response_tokens, 512)
        self.assertEqual(registry.profile("development").generation.max_user_message_bytes, 12900)
        self.assertLess(
            registry.document.resource_policies["development_desktop"].runtime_hard_limit_bytes,
            24 * 1024**3,
        )
        self.assertEqual(registry.profile("development").runtime.gpu_layers, "auto")
        self.assertTrue(registry.profile("development").runtime.mmap)
        self.assertEqual(registry.profile("development").runtime.cache_type_k, "q8_0")
        self.assertEqual(
            registry.profile("development").runtime.fit_context_min_tokens,
            self.document["models"][1]["runtime"]["fit_context_min_tokens"],
        )
        self.assertEqual(registry.document.openhands.sdk_version, "1.43.1")
        self.assertEqual(registry.openhands_sdk_python().name.lower(), "python.exe")
        self.assertEqual(registry.document.openhands.model_endpoint.port, 8081)
        self.assertEqual(
            registry.document.openhands.agent_server.tool_names,
            ["terminal", "file_editor", "task_tracker"],
        )
        self.assertIn("CONTRAT DE FIABILITÉ LÉA", registry.system_prompt("general"))
        development_prompt = registry.system_prompt("development")
        self.assertIn("CONTRAT DE FIABILITÉ LÉA", development_prompt)
        self.assertIn(
            "Cette demande ne relève pas du profil Programmation. Passe au profil Général.",
            development_prompt,
        )
        self.assertIn("événement outil réel", development_prompt)
        self.assertIn("Une sortie de terminal, même celle d'un test", development_prompt)
        self.assertIn("Ne révèle pas de raisonnement interne", development_prompt)
        public = registry.public_profiles()
        self.assertEqual([profile["id"] for profile in public], ["general", "development"])
        self.assertEqual(public[0]["max_user_message_bytes"], 6000)
        self.assertEqual(public[1]["max_user_message_bytes"], 12900)
        self.assertNotIn("model_path", public[0])
        self.assertNotIn("expected_sha256", public[0])
        self.assertEqual(public[1]["model_name"], "Qwen2.5-Coder-7B-Instruct Q6_K")
        self.assertEqual(public[1]["agent_engine"], "OpenHands")

    def test_7b_tool_template_uses_the_native_function_call_wrapper(self) -> None:
        """Pin the Qwen wrapper that llama.cpp natively parses on this GGUF.

        The official Qwen template is retained beside this focused variant for
        comparison.  The local Q6_K consistently emits ``<function_call>``;
        keeping that wrapper in the template's example and assistant history
        lets llama.cpp generate OpenAI ``tool_calls`` without a Python parser.
        """

        template = (
            PROJECT_DIRECTORY / self.document["models"][1]["chat_template_path"]
        ).read_text(encoding="utf-8")
        native_example = (
            '<function_call>\\n{\\"name\\": <function-name>, '
            '\\"arguments\\": <args-json-object>}\\n</function_call>'
        )
        escaped_example = (
            '<function_call>\\n{{\\"name\\": <function-name>, '
            '\\"arguments\\": <args-json-object>}}\\n</function_call>'
        )
        self.assertIn(native_example, template)
        self.assertNotIn(escaped_example, template)
        self.assertIn("Call exactly one function per assistant response.", template)
        self.assertNotIn("You may call one or more functions", template)

    def test_invalid_ids_names_hashes_and_types_are_rejected(self) -> None:
        """Les identités et types ambigus échouent avant tout lancement."""

        mutations = (
            (lambda data: data["profiles"][1].__setitem__("id", "general"), "uniques"),
            (lambda data: data["profiles"][0].__setitem__("display_name", " "), "vide"),
            (lambda data: data["models"][0].__setitem__("expected_sha256", "bad"), "expected_sha256"),
            (
                lambda data: data["openhands"]["agent_server"].__setitem__(
                    "image", "ghcr.io/openhands/agent-server@sha256:" + "z" * 64
                ),
                "digest SHA-256",
            ),
            (lambda data: data["models"][0].__setitem__("model_type", "unknown"), "model_type"),
        )
        for mutate, expected in mutations:
            with self.subTest(expected=expected):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaisesRegex(RegistryError, expected):
                    self.load(data)

    def test_workspace_root_must_be_exactly_ia_workspace(self) -> None:
        """A registry cannot expand Programming authority to a different L: directory."""

        data = copy.deepcopy(self.document)
        data["workspace_root"] = "L:\\Autre_Dossier"
        with self.assertRaisesRegex(RegistryError, "lecteur L"):
            self.load(data)

    def test_required_profiles_and_resource_thread_limit_are_rejected(self) -> None:
        """Le registre conserve les deux profils de base et leurs limites CPU centrales."""

        mutations = (
            (lambda data: data["profiles"].pop(), "Profils obligatoires absents"),
            (
                lambda data: data["models"][1]["runtime"].__setitem__("threads", 9),
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
                data["models"][0]["model_path"] = invalid_path
                with self.assertRaises(RegistryError):
                    self.load(data)

    def test_disabled_profile_keeps_a_path_confined_to_models(self) -> None:
        """Un profil inactif ne peut pas devenir plus tard une référence extérieure."""

        data = copy.deepcopy(self.document)
        data["profiles"][1]["enabled"] = False
        data["models"][1]["model_path"] = "C:/outside.gguf"
        with self.assertRaisesRegex(RegistryError, "chemin relatif|sous"):
            self.load(data)

    def test_incoherent_context_slots_and_resource_thresholds_are_rejected(self) -> None:
        """Les budgets sans entrée et les seuils inversés ne peuvent pas démarrer."""

        mutations = (
            lambda data: data["models"][0].__setitem__("context_tokens", 1000),
            lambda data: data["models"][0]["runtime"].__setitem__("parallel_slots", 2),
            lambda data: data["models"][1]["runtime"].__setitem__("fit_context_min_tokens", 4096),
            lambda data: data["models"][1].__setitem__("context_tokens", 19_999),
            lambda data: data["models"][1].__setitem__("context_tokens", 24_000),
            lambda data: data["models"][1]["runtime"].__setitem__("cache_type_k", "unsafe"),
            lambda data: data["resource_policies"]["general_desktop"].__setitem__(
                "runtime_warning_bytes", 20000000000
            ),
            lambda data: data["resource_policies"]["development_desktop"].__setitem__(
                "runtime_hard_limit_bytes", 24 * 1024**3
            ),
            lambda data: data["profiles"][1]["generation"].__setitem__(
                "max_user_message_bytes", 18929
            ),
            lambda data: data["agent_policy"].__setitem__(
                "max_action_response_tokens", 2049
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaises(RegistryError):
                    self.load(data)

    def test_openhands_sdk_context_floor_is_checked_before_launch(self) -> None:
        """Le budget utilisateur seul ne suffit pas au condenser du SDK épinglé."""

        data = copy.deepcopy(self.document)
        data["models"][1]["context_tokens"] = 16_000
        data["models"][1]["runtime"]["fit_context_min_tokens"] = 16_000
        data["profiles"][1]["generation"]["max_user_message_bytes"] = 1000
        with self.assertRaisesRegex(RegistryError, "insuffisant pour le SDK"):
            self.load(data)

    def test_openhands_engine_metadata_and_model_integrity_are_checked(self) -> None:
        """Le cerveau, le SDK et ses outils restent cohérents dans une seule source."""

        invalid_mutations = (
            lambda data: data["profiles"][1].__setitem__("agent_engine", "direct"),
            lambda data: data["models"][1].__setitem__("engine", "unsupported"),
            lambda data: data["openhands"]["agent_server"].__setitem__("host", "0.0.0.0"),
            lambda data: data["openhands"]["agent_server"].__setitem__("tool_names", ["terminal"]),
            lambda data: data["profiles"][1].__setitem__("tools", ["terminal"]),
            lambda data: data["models"][1].__setitem__("expected_chat_template_sha256", "bad"),
            lambda data: data["openhands"]["agent_runtime"].__setitem__("state_volume", "bad volume"),
        )
        for mutate in invalid_mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaises(RegistryError):
                    self.load(data)

        data = copy.deepcopy(self.document)
        data["models"][1]["expected_size_bytes"] = 4
        data["models"][1]["expected_sha256"] = hashlib.sha256(b"test").hexdigest()
        registry = self.load(data)
        self.assertEqual(registry.verify_model_integrity("development").read_bytes(), b"test")

    def test_model_replacement_is_resolved_without_changing_profile_contract(self) -> None:
        """Un nouveau modèle déclaré remplace le cerveau sans copier les permissions."""

        data = copy.deepcopy(self.document)
        replacement = copy.deepcopy(data["models"][1])
        replacement.update(id="compatible-model", model_name="Modèle compatible de test")
        replacement["runtime"]["alias"] = "compatible-alias"
        data["models"].append(replacement)
        data["profiles"][1]["model_id"] = replacement["id"]
        registry = self.load(data)

        resolved = registry.profile("development")
        self.assertEqual(resolved.model.id, "compatible-model")
        self.assertEqual(resolved.runtime.alias, "compatible-alias")
        self.assertEqual(resolved.tools, data["profiles"][1]["tools"])
        self.assertEqual(resolved.workspace_permission, "ia_workspace_project")
        self.assertEqual(registry.public_profiles()[1]["model_name"], replacement["model_name"])
        self.assertEqual(registry.launcher_document()["profiles"][1]["model_path"], replacement["model_path"])

    def test_unknown_model_engine_and_duplicate_configuration_are_rejected(self) -> None:
        """Une référence inconnue ou une seconde source de paramètres échoue explicitement."""

        mutations = (
            lambda data: data["profiles"][1].__setitem__("model_id", "absent"),
            lambda data: data["models"][1].__setitem__("engine", "colibri"),
            lambda data: data["models"].append(copy.deepcopy(data["models"][0])),
            lambda data: data["profiles"][0].__setitem__("context_tokens", 8192),
            lambda data: data["models"][1].__setitem__("capabilities", []),
            lambda data: data["models"][1].__setitem__("capabilities", ["chat"]),
            lambda data: data.__setitem__("schema_version", 2),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaises(RegistryError):
                    self.load(data)

    def test_two_profiles_share_a_model_without_sharing_permissions_or_prompts(self) -> None:
        """Une seule définition modèle suffit ; chaque contrat de profil reste distinct."""

        data = copy.deepcopy(self.document)
        data["profiles"][0]["model_id"] = data["models"][1]["id"]
        registry = self.load(data)
        general = registry.profile("general")
        development = registry.profile("development")

        self.assertIs(general.model, development.model)
        self.assertEqual(general.runtime.alias, development.runtime.alias)
        self.assertEqual(general.tools, [])
        self.assertEqual(general.workspace_permission, "none")
        self.assertEqual(development.tools, ["terminal", "file_editor", "task_tracker"])
        self.assertNotEqual(registry.system_prompt("general"), registry.system_prompt("development"))
        self.assertEqual(len(registry.document.models), 2)

    def test_model_configuration_cannot_remove_profile_requirements_or_grant_permissions(self) -> None:
        """Les capacités déclarées du cerveau ne sont jamais une autorisation d’outils."""

        mutations = (
            lambda data: data["profiles"][1].__setitem__("required_model_capabilities", ["chat"]),
            lambda data: data["profiles"][1].__setitem__("model_id", data["models"][0]["id"]),
            lambda data: data["profiles"][0].__setitem__("tools", ["terminal"]),
            lambda data: data["workspace_permissions"]["none"].__setitem__("read", True),
            lambda data: data.__setitem__("default_profile_id", "development"),
            lambda data: data["models"][1]["runtime"].__setitem__("skip_chat_parsing", True),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.document)
                mutate(data)
                with self.assertRaises(RegistryError):
                    self.load(data)

    def test_malformed_json_is_reported_as_a_registry_error(self) -> None:
        """Le chargeur transforme un JSON tronqué en erreur de configuration lisible."""

        path = self.root / "config" / "models.json"
        path.write_text('{"models":', encoding="utf-8")
        with self.assertRaisesRegex(RegistryError, "Registre des modèles invalide"):
            load_model_registry(path, project_root=self.root)

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
        self.assertEqual(payload["profiles"][0]["max_user_message_bytes"], 6000)
        self.assertEqual(payload["profiles"][1]["max_user_message_bytes"], 12900)
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
        """Le lanceur direct reste lié au registre et ne peut pas lancer OpenHands au mauvais port."""

        script = (PROJECT_DIRECTORY / "lea.ps1").read_text(encoding="utf-8")

        self.assertIn("$ModelRuntimePort = [int]$ModelRegistry.runtime.port", script)
        self.assertIn("Port = $ModelRuntimePort", script)
        self.assertIn("Endpoint = $ModelRuntimeModelsEndpoint", script)
        self.assertNotIn("Port = 8080", script)
        self.assertIn("$profile.agent_engine -ne 'direct'", script)
        self.assertIn("contrôleur OpenHands de Léa", script)

    def test_powershell_rejects_wrong_json_types_before_status(self) -> None:
        """Le lanceur refuse les chaînes déguisées en port ou booléen avant tout run."""

        invalid_documents = (
            (lambda data: data["runtime"].__setitem__("port", "8080"), "runtime.port"),
            (lambda data: data["profiles"][0].__setitem__("enabled", "false"), "profiles.0.enabled"),
            (lambda data: data["models"][1].__setitem__("context_tokens", 24_000), "fit"),
            (
                lambda data: data["resource_policies"]["development_desktop"].__setitem__(
                    "runtime_hard_limit_bytes", 24 * 1024**3
                ),
                "strictement inférieure à 24 GiB",
            ),
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

"""Contrats du seul adaptateur réel, sans téléchargement ni lancement de poids."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.inference import (  # noqa: E402
    ModelResponseError,
    ModelUnavailableError,
    inference_adapter,
    llama_cpp_arguments,
)
from app.model_registry import load_model_registry  # noqa: E402


class InferenceTests(unittest.IsolatedAsyncioTestCase):
    """Vérifie commandes et protocole avec les paramètres officiels et HTTP simulé."""

    def setUp(self) -> None:
        """Charge le registre réel sans lancer de processus ni lire tout le GGUF."""

        self.registry = load_model_registry()

    def test_commands_preserve_model_parameters_and_quote_paths(self) -> None:
        """Les deux propriétaires reçoivent le contexte, les caches et le slot configurés."""

        for profile_id in ("general", "development"):
            with self.subTest(profile=profile_id):
                adapter = inference_adapter(self.registry, profile_id)
                profile = self.registry.profile(profile_id)
                command = adapter.launch_command()
                args = command["arguments"]
                for option, value in (
                    ("--ctx-size", profile.context_tokens),
                    ("--parallel", 1),
                    ("--alias", profile.runtime.alias),
                    ("--cache-type-k", profile.runtime.cache_type_k),
                    ("--fit", "on" if profile.runtime.fit else "off"),
                ):
                    self.assertEqual(args[args.index(option) + 1], str(value))
                self.assertEqual(args[args.index("-m") + 1], str(self.registry.model_path(profile_id)))
                self.assertEqual(args[args.index("--port") + 1], str(adapter.endpoint.port))
                self.assertNotIn("powershell", command["executable"])
        development = inference_adapter(self.registry, "development").launch_command()["arguments"]
        self.assertLess(development.index("--jinja"), development.index("--chat-template-file"))
        general = inference_adapter(self.registry, "general").launch_command()["arguments"]
        self.assertNotIn("--chat-template-file", general)

    def test_configuration_flags_are_not_silently_ignored(self) -> None:
        """Les options fausses se traduisent aussi explicitement pour éviter les défauts moteur."""

        configuration = inference_adapter(self.registry, "general").launch_configuration()
        configuration["runtime"]["mmap"] = False
        configuration["runtime"]["skip_chat_parsing"] = True
        arguments = llama_cpp_arguments(configuration)
        self.assertIn("--no-mmap", arguments)
        self.assertIn("--skip-chat-parsing", arguments)
        self.assertNotIn("--no-skip-chat-parsing", arguments)

    async def test_http_request_uses_the_selected_model_and_budget(self) -> None:
        """Le transport simulé reçoit exactement l’alias et les messages de l’appelant."""

        requests = []

        def respond(request: httpx.Request) -> httpx.Response:
            """Observe le payload sans ouvrir de socket, puis renvoie une réponse standard."""

            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "Réponse"}}]})

        adapter = inference_adapter(self.registry, "general")
        messages = [{"role": "user", "content": "Bonjour"}]
        answer = await adapter.generate(messages, transport=httpx.MockTransport(respond))
        payload = json.loads(requests[0].content)
        self.assertEqual(answer, "Réponse")
        self.assertEqual(payload["model"], self.registry.profile("general").runtime.alias)
        self.assertEqual(payload["max_tokens"], 1024)
        self.assertEqual(payload["messages"], messages)
        self.assertEqual(str(requests[0].url), adapter.chat_url)

    async def test_readiness_requires_the_expected_alias_and_valid_json(self) -> None:
        """Une API accessible ne prouve pas que le bon modèle est chargé."""

        adapter = inference_adapter(self.registry, "development")
        for payload, expected in (
            ({"data": [{"id": adapter.profile.runtime.alias}]}, True),
            ({"data": [{"id": "wrong-model"}]}, False),
            ({"data": None}, False),
            ([], False),
        ):
            with self.subTest(payload=payload):
                def respond(request: httpx.Request) -> httpx.Response:
                    """Émet la variante de readiness de ce cas sans service réel."""

                    return httpx.Response(200, json=payload)

                self.assertEqual(
                    await adapter.is_ready(transport=httpx.MockTransport(respond)), expected
                )

    async def test_http_errors_are_safe_and_explicit(self) -> None:
        """Une panne réseau, un statut d’erreur ou un contenu invalide ne devient pas une réponse."""

        adapter = inference_adapter(self.registry, "general")

        def unavailable(request: httpx.Request) -> httpx.Response:
            """Simule une connexion refusée au moteur local."""

            raise httpx.ConnectError("private diagnostic", request=request)

        with self.assertRaises(ModelUnavailableError):
            await adapter.generate([], transport=httpx.MockTransport(unavailable))
        for status, payload in ((500, {}), (200, {}), (200, {"choices": []})):
            with self.subTest(status=status, payload=payload):
                def respond(request: httpx.Request) -> httpx.Response:
                    """Retourne une réponse inutilisable pour ce cas."""

                    return httpx.Response(status, json=payload)

                with self.assertRaises(ModelResponseError):
                    await adapter.generate([], transport=httpx.MockTransport(respond))

    def test_sdk_configuration_is_model_driven(self) -> None:
        """Le port, le préfixe API et les stops SDK proviennent du registre."""

        adapter = inference_adapter(self.registry, "development")
        endpoint = self.registry.document.openhands.model_endpoint
        self.assertEqual(adapter.sdk_base_url, f"http://host.docker.internal:{endpoint.port}/v1")
        self.assertEqual(adapter.sdk_extra_body()["stop"], adapter.profile.model.stop_sequences)
        self.assertFalse(adapter.sdk_extra_body()["parallel_tool_calls"])
        self.assertNotIn("stop", inference_adapter(self.registry, "general").sdk_extra_body())


if __name__ == "__main__":
    unittest.main()

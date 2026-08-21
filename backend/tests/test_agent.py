from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.agent import AgentRunManager, AgentRunRecord, AgentRunner  # noqa: E402
from app.model_registry import AgentPolicy, load_model_registry  # noqa: E402
from app.tool_calling import (  # noqa: E402
    AssistantTurn,
    ParsedToolCall,
    ToolArgumentsError,
    ToolAuthorizationError,
)


def call_turn(name: str, arguments: dict[str, Any], call_id: str) -> AssistantTurn:
    """Produit le même objet canonique que le parseur OpenAI après validation."""

    assistant_message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
        ],
    }
    return AssistantTurn(
        None,
        ParsedToolCall(call_id, name, arguments, assistant_message),
        "tool_calls",
    )


class ScriptedGateway:
    """Retourne des tours déterministes et conserve le transcript reçu."""

    def __init__(self, *turns: AssistantTurn | BaseException) -> None:
        """Accepte aussi une exception pour simuler un refus de protocole."""

        self.turns = list(turns)
        self.calls: list[list[dict[str, Any]]] = []

    async def complete(self, messages, tools):
        """Copie le transcript puis consomme exactement un résultat scripté."""

        self.calls.append([message.copy() for message in messages])
        turn = self.turns.pop(0)
        if isinstance(turn, BaseException):
            raise turn
        return turn


class BlockingGateway:
    """Attend indéfiniment pour rendre l'annulation du modèle déterministe."""

    def __init__(self) -> None:
        """Expose un événement qui prouve le début de l'appel."""

        self.started = asyncio.Event()

    async def complete(self, messages, tools):
        """Bloque jusqu'à l'annulation de la tâche HTTP par le runner."""

        self.started.set()
        await asyncio.Event().wait()


class FakeDevelopmentTools:
    """Compte les demandes d'annulation sans créer de processus."""

    def __init__(self) -> None:
        """Commence sans run annulé."""

        self.cancelled: list[str] = []

    async def cancel_run(self, run_id: str) -> int:
        """Enregistre l'UUID et simule un arbre possédé arrêté."""

        self.cancelled.append(run_id)
        return 0


class FakeDispatcher:
    """Simule un catalogue unique en reproduisant succès et erreurs typées."""

    def __init__(self) -> None:
        """Expose read_file et une trace de toutes les exécutions."""

        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.development_tools = FakeDevelopmentTools()

    def supports(self, name: str) -> bool:
        """N'annonce qu'un outil volontairement minimal."""

        return name == "read_file"

    def schemas(self, allowed_tools: list[str]) -> list[dict[str, Any]]:
        """Retourne un schéma compact afin de garder le budget des tests prévisible."""

        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Lecture",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]

    async def execute(self, name, arguments, *, allowed_tools, run_id):
        """Refuse `bad` comme argument corrigeable et réussit les autres lectures."""

        if name not in allowed_tools:
            raise ToolAuthorizationError("interdit")
        self.calls.append((name, arguments.copy()))
        if arguments.get("path") == "bad":
            raise ToolArgumentsError("chemin invalide")
        return {"path": arguments["path"], "content": "ok"}


class AgentRunnerTests(unittest.IsolatedAsyncioTestCase):
    """Valide états, limites, récupération et annulation indépendamment du vrai modèle."""

    def setUp(self) -> None:
        """Charge le vrai profil Programmation mais remplace modèle et outils par des doubles."""

        root = Path(__file__).resolve().parents[2]
        self.registry = load_model_registry(project_root=root)
        self.profile = self.registry.profile("development")
        self.policy = self.registry.document.agent_policy
        self.dispatcher = FakeDispatcher()

    def runner(self, gateway, **overrides: int) -> AgentRunner:
        """Construit une politique dérivée strictement validée pour chaque scénario."""

        policy = AgentPolicy.model_validate({**self.policy.model_dump(), **overrides})
        return AgentRunner(self.registry, self.dispatcher, gateway, policy)

    async def test_successful_tool_result_and_final_report(self) -> None:
        """Un résultat structuré est renvoyé au modèle avant le rapport final."""

        gateway = ScriptedGateway(
            call_turn("read_file", {"path": "src/été.ts"}, "call_1"),
            AssistantTurn("Analyse terminée et vérifiée.", None, "stop"),
        )
        record = AgentRunRecord("11111111-1111-1111-1111-111111111111", "Analyse", "development", "project")
        result = await self.runner(gateway).run(record, self.profile)
        self.assertEqual(result.state, "completed")
        self.assertEqual(result.action_count, 1)
        self.assertEqual(result.report, "Analyse terminée et vérifiée.")
        self.assertEqual(gateway.calls[1][-1]["role"], "tool")
        self.assertIn('"ok":true', gateway.calls[1][-1]["content"])

    async def test_correctable_error_is_returned_but_repetition_stops(self) -> None:
        """Une première erreur nourrit le modèle; trois erreurs identiques bornent la boucle."""

        recovered_gateway = ScriptedGateway(
            call_turn("read_file", {"path": "bad"}, "call_1"),
            AssistantTurn("Blocage expliqué après lecture refusée.", None, "stop"),
        )
        recovered = AgentRunRecord("22222222-2222-2222-2222-222222222222", "Analyse", "development", "project")
        await self.runner(recovered_gateway).run(recovered, self.profile)
        self.assertEqual(recovered.state, "completed")
        self.assertEqual(recovered.events[0]["state"], "failed")
        self.assertIn('"ok":false', recovered_gateway.calls[1][-1]["content"])

        repeated_gateway = ScriptedGateway(
            call_turn("read_file", {"path": "bad"}, "call_1"),
            call_turn("read_file", {"path": "bad"}, "call_2"),
            call_turn("read_file", {"path": "bad"}, "call_3"),
        )
        repeated = AgentRunRecord("33333333-3333-3333-3333-333333333333", "Analyse", "development", "project")
        await self.runner(repeated_gateway).run(repeated, self.profile)
        self.assertEqual(repeated.state, "limit_reached")
        self.assertEqual(repeated.action_count, 3)

    async def test_action_limit_and_forbidden_action_are_terminal(self) -> None:
        """Les limites externes et l'autorisation restent prioritaires sur le modèle."""

        limited_gateway = ScriptedGateway(call_turn("read_file", {"path": "a"}, "call_1"))
        limited = AgentRunRecord("44444444-4444-4444-4444-444444444444", "Analyse", "development", "project")
        await self.runner(limited_gateway, max_actions=1).run(limited, self.profile)
        self.assertEqual(limited.state, "limit_reached")

        forbidden_gateway = ScriptedGateway(ToolAuthorizationError("outil absent"))
        forbidden = AgentRunRecord("55555555-5555-5555-5555-555555555555", "Analyse", "development", "project")
        await self.runner(forbidden_gateway).run(forbidden, self.profile)
        self.assertEqual(forbidden.state, "failed")
        self.assertIn("outil absent", forbidden.error)

    async def test_manager_cancels_a_blocked_model_call(self) -> None:
        """L'annulation utilisateur réveille la boucle sans attendre le timeout HTTP."""

        gateway = BlockingGateway()
        manager = AgentRunManager()
        record = await manager.start("Analyse", self.profile, "project", self.runner(gateway))
        await asyncio.wait_for(gateway.started.wait(), timeout=2)
        await manager.cancel(record.run_id)
        task = manager.tasks[record.run_id]
        result = await asyncio.wait_for(task, timeout=2)
        self.assertEqual(result.state, "cancelled")
        self.assertIn(record.run_id, self.dispatcher.development_tools.cancelled)
        await manager.close()


if __name__ == "__main__":
    unittest.main()

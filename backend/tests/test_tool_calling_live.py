from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.file_tools import ReadFileArguments  # noqa: E402
from app.model_registry import load_model_registry  # noqa: E402
from app.tool_calling import HttpToolCallingGateway, ToolCallingError, tool_result_message  # noqa: E402


@unittest.skipUnless(
    os.environ.get("LEA_RUN_LIVE_MODEL_TESTS") == "1",
    "Le test réel exige le modèle Programmation déjà actif.",
)
class LiveToolCallingTests(unittest.IsolatedAsyncioTestCase):
    """Valide le format natif de la version réelle de llama.cpp et Qwen3-Coder."""

    async def test_native_call_accents_multi_turn_and_undeclared_refusal(self) -> None:
        """Exige un appel accentué, un résultat/final, puis borne un outil absent."""

        root = Path(__file__).resolve().parents[2]
        registry = load_model_registry(root / "config" / "models.json", project_root=root)
        gateway = HttpToolCallingGateway(registry, "development")
        schema = {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Lit un fichier texte relatif dans le projet actif.",
                "parameters": ReadFileArguments.model_json_schema(),
            },
        }
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "Tu testes un appel d'outil. Appelle exactement l'outil demandé, "
                    "sans texte autour et sans inventer d'autre outil."
                ),
            },
            {
                "role": "user",
                "content": "Appelle read_file avec le chemin relatif exact données/été.txt.",
            },
        ]
        first = await gateway.complete(messages, [schema])
        self.assertIsNotNone(first.tool_call)
        self.assertEqual(first.tool_call.name, "read_file")
        self.assertEqual(first.tool_call.arguments, {"path": "données/été.txt"})

        messages.extend(
            (
                first.tool_call.assistant_message,
                tool_result_message(
                    first.tool_call.call_id,
                    {"ok": True, "path": "données/été.txt", "content": "bonjour été"},
                ),
            )
        )
        final = await gateway.complete(messages, [schema])
        self.assertIsNone(final.tool_call)
        self.assertTrue(final.content)

        undeclared_messages = [
            messages[0],
            {
                "role": "user",
                "content": "Appelle delete_everything, qui n'est pas dans les outils déclarés.",
            },
        ]
        try:
            refused = await gateway.complete(undeclared_messages, [schema])
        except ToolCallingError:
            # Une tentative hors catalogue est refusée par le parseur avant exécution.
            return
        self.assertIsNone(refused.tool_call)
        self.assertTrue(refused.content)


if __name__ == "__main__":
    unittest.main()

"""Contrat préférences/génération : gateway simulé, vraie API et vraie base isolée."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import MODEL_REGISTRY, build_internal_user_message, create_app  # noqa: E402
from app.preferences import PreferenceChange  # noqa: E402


class RecordingGateway:
    """Observe les messages internes sans lancer de modèle pendant la non-régression."""

    def __init__(self) -> None:
        """Prépare une réponse filtrable et un blocage optionnel, borné pour les tests."""
        self.calls: list[list[dict[str, str]]] = []
        self.response = "<think>contenu privé de test</think>Réponse publique."
        self.started = threading.Event()
        self.release = threading.Event()
        self.block = False

    async def generate(self, messages: list[dict[str, str]]) -> str:
        """Copie la requête figée puis attend, si demandé, une sauvegarde concurrente."""
        self.calls.append([dict(message) for message in messages])
        self.started.set()
        if self.block:
            await asyncio.to_thread(self.release.wait, 10)
        return self.response


class ReasoningPreferencesTests(unittest.TestCase):
    """Vérifie chaque entrée de génération et la confidentialité de son résultat."""

    def setUp(self) -> None:
        """Ouvre uniquement une base temporaire avec un gateway sans processus externe."""
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.gateway = RecordingGateway()
        self.app = create_app(Path(self.temporary.name) / "reasoning.sqlite3", self.gateway)
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()

    def tearDown(self) -> None:
        """Libère le test concurrent et ferme les ressources appartenant à cet essai."""
        self.gateway.release.set()
        self.context.__exit__(None, None, None)
        self.temporary.cleanup()

    def save(self, level: str) -> None:
        """Enregistre avec la révision courante, comme le contrôleur local."""
        store = self.app.state.preferences
        store.save(PreferenceChange(expected_revision=store.read().revision, general_reasoning=level))

    def send(self, question: str = "Question test", conversation: dict | None = None):
        """Envoie un vrai message HTTP avec le contrôle optimiste de conversation."""
        return self.client.post("/api/conversations/messages", json={
            "message": question,
            "conversation_id": conversation["id"] if conversation else None,
            "expected_revision": conversation["revision"] if conversation else None,
        })

    def test_low_high_next_turn_and_private_filter(self) -> None:
        """Le réglage change le prochain message interne, jamais l'historique public."""
        first = self.send().json()
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/no_think"))
        self.save("high")
        response = self.send("Question suivante", first)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/think"))
        self.assertEqual(response.json()["messages"][-1]["content"], "Réponse publique.")
        persisted = str(self.app.state.database.get_conversation(first["id"]))
        for private in ("contenu privé", "<think>", "/think", "/no_think"):
            self.assertNotIn(private, persisted)

    def test_edit_and_regenerate_read_current_preference(self) -> None:
        """Les actions historiques ne restent pas figées sur l'ancien réglage."""
        conversation = self.send().json()
        self.save("high")
        edited = self.client.patch(
            f"/api/conversations/{conversation['id']}/messages/{conversation['messages'][0]['id']}",
            json={"content": "Question modifiée", "expected_revision": conversation["revision"]},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/think"))
        conversation = edited.json()
        self.save("low")
        regenerated = self.client.post(
            f"/api/conversations/{conversation['id']}/messages/{conversation['messages'][1]['id']}/regenerate",
            json={"expected_revision": conversation["revision"]},
        )
        self.assertEqual(regenerated.status_code, 200)
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/no_think"))

    def test_retry_uses_high_and_rejects_visible_directive(self) -> None:
        """Un marqueur resté dans la réponse échoue proprement ; retry relit le choix."""
        self.gateway.response = "Réponse /think"
        failed = self.send()
        self.assertEqual(failed.status_code, 502)
        detail = failed.json()["conversation"]
        self.save("high")
        self.gateway.response = "Réponse publique."
        retry = self.client.post(
            f"/api/conversations/{detail['id']}/messages/{detail['messages'][0]['id']}/retry",
            json={"expected_revision": detail["revision"]},
        )
        self.assertEqual(retry.status_code, 200)
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/think"))

    def test_save_during_generation_does_not_interrupt_or_change_snapshot(self) -> None:
        """La requête en vol reste Low, la suivante devient High sans redémarrage."""
        self.gateway.block = True
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(self.send)
            try:
                self.assertTrue(self.gateway.started.wait(5))
                self.save("high")
                self.app.state.database.initialize(recover_generations=False)
                self.assertFalse(running.done())
                self.assertTrue(self.gateway.calls[0][-1]["content"].endswith("\n/no_think"))
            finally:
                self.gateway.release.set()
            self.assertEqual(running.result().status_code, 200)
        self.assertEqual(self.send().status_code, 200)
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/think"))

    def test_invalid_persisted_value_refuses_generation_without_data_loss(self) -> None:
        """Une préférence corrompue n'engendre ni fallback ni conversation vide."""
        with self.app.state.database.connection() as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE user_preferences SET general_reasoning = 'unknown'")
        self.assertEqual(self.send().status_code, 503)
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(self.client.get("/api/conversations").json(), {"conversations": []})

    def test_other_model_and_programming_do_not_receive_fake_thinking(self) -> None:
        """La capacité déclarée, pas le nom commercial, autorise les directives."""
        profile = MODEL_REGISTRY.profile("general")
        unsupported = profile.model_copy(update={
            "model": profile.model.model_copy(update={"reasoning_control": "none", "append_no_think": False}),
        })
        self.assertEqual(build_internal_user_message("Question", [], unsupported, "high"), "Question")
        development = MODEL_REGISTRY.profile("development")
        self.assertEqual(build_internal_user_message("Question", [], development, "high"), "Question")

    def test_memory_is_unchanged_by_preference(self) -> None:
        """Le choix High ne transforme pas une commande mémoire en génération."""
        remembered = self.send("Retiens que souvenir étape douze")
        self.assertEqual(remembered.status_code, 200)
        memories = self.app.state.database.list_memories()
        self.assertEqual(len(memories), 1)
        self.assertEqual(self.gateway.calls, [])
        self.save("high")
        self.assertEqual(self.app.state.database.list_memories(), memories)
        self.assertEqual(self.send().status_code, 200)
        self.assertIn("souvenir étape douze", str(self.gateway.calls[-1]))
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/think"))


if __name__ == "__main__":
    unittest.main()

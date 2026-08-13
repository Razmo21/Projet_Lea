from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIRECTORY))

from app.main import (  # noqa: E402
    ModelUnavailableError,
    create_app,
)


class FakeModelGateway:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses) or ["Réponse de Léa"]
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls.append([message.copy() for message in messages])
        response = self.responses.pop(0) if self.responses else "Réponse de Léa"
        if isinstance(response, BaseException):
            raise response
        return str(response)


class BlockingModelGateway:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    async def generate(self, messages: list[dict[str, str]]) -> str:
        self.calls += 1
        self.started.set()
        await asyncio.to_thread(self.release.wait, 10)
        return "Réponse concurrente"


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-api-test-", dir=Path(__file__).resolve().parent
        )
        self.database_path = Path(self.temporary_directory.name) / "api.sqlite3"
        self.gateway = FakeModelGateway()
        self.application = create_app(self.database_path, self.gateway)
        self.client_context = TestClient(self.application)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.temporary_directory.cleanup()

    def send(self, message: str, conversation: dict | None = None):
        return self.client.post(
            "/api/conversations/messages",
            json={
                "conversation_id": conversation["id"] if conversation else None,
                "message": message,
                "expected_revision": conversation["revision"] if conversation else None,
            },
        )

    def test_first_message_creates_persistent_conversation_from_original_text(self) -> None:
        response = self.send("  Bonjour Léa  ")

        self.assertEqual(response.status_code, 200)
        conversation = response.json()
        self.assertEqual(
            [message["content"] for message in conversation["messages"]],
            ["Bonjour Léa", "Réponse de Léa"],
        )
        self.assertEqual(conversation["title"], "Bonjour Léa")
        self.assertTrue(self.gateway.calls[-1][-1]["content"].endswith("\n/no_think"))
        self.assertNotIn("/no_think", response.text)

        with closing(sqlite3.connect(self.database_path)) as connection:
            persisted = " ".join(
                row[0] for row in connection.execute("SELECT content FROM messages")
            )
            roles = [row[0] for row in connection.execute("SELECT role FROM messages")]
        self.assertNotIn("/no_think", persisted)
        self.assertNotIn("<think>", persisted.lower())
        self.assertNotIn("system", roles)

    def test_list_read_search_rename_and_delete(self) -> None:
        conversation = self.send("Éléphant spécial").json()
        listed = self.client.get("/api/conversations").json()["conversations"]
        self.assertEqual([item["id"] for item in listed], [conversation["id"]])
        self.assertEqual(
            self.client.get("/api/conversations", params={"search": "ÉLÉPHANT"}).json()[
                "conversations"
            ][0]["id"],
            conversation["id"],
        )
        self.assertEqual(
            self.client.get(f"/api/conversations/{conversation['id']}").status_code,
            200,
        )

        renamed_response = self.client.patch(
            f"/api/conversations/{conversation['id']}",
            json={"title": "Titre <b>affiché comme texte</b>", "expected_revision": conversation["revision"]},
        )
        self.assertEqual(renamed_response.status_code, 200)
        renamed = renamed_response.json()
        self.assertEqual(renamed["title_origin"], "manual")
        self.assertIn("<b>", renamed["title"])

        deleted = self.client.request(
            "DELETE",
            f"/api/conversations/{conversation['id']}",
            json={"expected_revision": renamed["revision"]},
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/conversations").json()["conversations"], [])
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_failed_generation_remains_retryable_without_fake_assistant(self) -> None:
        self.gateway.responses = [
            ModelUnavailableError("indisponible"),
            "Réponse après reprise",
        ]
        failed_response = self.send("Question à réessayer")

        self.assertEqual(failed_response.status_code, 503)
        failed = failed_response.json()["conversation"]
        self.assertEqual(len(failed["messages"]), 1)
        self.assertEqual(failed["messages"][0]["status"], "failed")

        retried = self.client.post(
            f"/api/conversations/{failed['id']}/messages/{failed['messages'][0]['id']}/retry",
            json={"expected_revision": failed["revision"]},
        )
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(
            [message["content"] for message in retried.json()["messages"]],
            ["Question à réessayer", "Réponse après reprise"],
        )

    def test_edit_and_regeneration_are_destructive_and_assistant_cannot_be_edited(self) -> None:
        self.gateway.responses = ["R1", "R2", "Nouvelle R1", "Régénérée"]
        first = self.send("Q1").json()
        second = self.send("Q2", first).json()
        assistant = second["messages"][1]
        refused = self.client.patch(
            f"/api/conversations/{second['id']}/messages/{assistant['id']}",
            json={"content": "Interdit", "expected_revision": second["revision"]},
        )
        self.assertEqual(refused.status_code, 400)

        user = second["messages"][0]
        edited_response = self.client.patch(
            f"/api/conversations/{second['id']}/messages/{user['id']}",
            json={"content": "Q1 modifiée", "expected_revision": second["revision"]},
        )
        self.assertEqual(edited_response.status_code, 200)
        edited = edited_response.json()
        self.assertEqual(
            [message["content"] for message in edited["messages"]],
            ["Q1 modifiée", "Nouvelle R1"],
        )

        regenerated_response = self.client.post(
            f"/api/conversations/{edited['id']}/messages/{edited['messages'][1]['id']}/regenerate",
            json={"expected_revision": edited["revision"]},
        )
        self.assertEqual(regenerated_response.status_code, 200)
        self.assertEqual(
            [message["content"] for message in regenerated_response.json()["messages"]],
            ["Q1 modifiée", "Régénérée"],
        )

    def test_stale_revision_and_foreign_origin_are_rejected(self) -> None:
        conversation = self.send("Question").json()
        first_tab = self.client.patch(
            f"/api/conversations/{conversation['id']}",
            json={"title": "Premier onglet", "expected_revision": conversation["revision"]},
        )
        self.assertEqual(first_tab.status_code, 200)
        second_tab = self.client.patch(
            f"/api/conversations/{conversation['id']}",
            json={"title": "Second onglet", "expected_revision": conversation["revision"]},
        )
        self.assertEqual(second_tab.status_code, 409)
        self.assertEqual(
            self.client.get(f"/api/conversations/{conversation['id']}").json()["title"],
            "Premier onglet",
        )

        foreign = self.client.post(
            "/api/conversations/messages",
            headers={"Origin": "https://example.com"},
            json={"conversation_id": None, "message": "Interdit", "expected_revision": None},
        )
        self.assertEqual(foreign.status_code, 403)

    def test_missing_conversation_and_message_return_404(self) -> None:
        missing_conversation_id = "123e4567-e89b-42d3-a456-426614174000"
        missing_message_id = "223e4567-e89b-42d3-a456-426614174000"
        self.assertEqual(
            self.client.get(
                f"/api/conversations/{missing_conversation_id}"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/conversations/messages",
                json={
                    "conversation_id": missing_conversation_id,
                    "message": "Question",
                    "expected_revision": 0,
                },
            ).status_code,
            404,
        )

        conversation = self.send("Question existante").json()
        self.assertEqual(
            self.client.post(
                f"/api/conversations/{conversation['id']}/messages/{missing_message_id}/retry",
                json={"expected_revision": conversation["revision"]},
            ).status_code,
            404,
        )

    def test_invalid_payloads_are_rejected_before_the_model(self) -> None:
        invalid_payloads = (
            {"conversation_id": None, "message": " ", "expected_revision": None},
            {"conversation_id": None, "message": "nul\x00ici", "expected_revision": None},
            {"conversation_id": None, "message": "x" * 6001, "expected_revision": None},
            {"conversation_id": None, "message": "<think>secret</think>", "expected_revision": None},
            {"conversation_id": None, "message": "/no_think", "expected_revision": None},
            {"conversation_id": None, "message": "Bonjour", "expected_revision": None, "history": []},
            {"conversation_id": None, "message": "Bonjour", "expected_revision": None, "role": "system"},
            {"conversation_id": None, "message": "Bonjour", "expected_revision": None, "extra": True},
            {"conversation_id": "invalid", "message": "Bonjour", "expected_revision": 0},
        )
        calls_before = len(self.gateway.calls)
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/api/conversations/messages", json=payload).status_code,
                    422,
                )
        self.assertEqual(len(self.gateway.calls), calls_before)

    def test_model_thinking_is_filtered_and_empty_filtered_answer_fails(self) -> None:
        self.gateway.responses = [
            "< THINK >secret externe <think>secret interne</think>"
            " encore secret< / THINK >Réponse finale",
            "</think>",
        ]
        filtered_response = self.send("Première question")
        self.assertEqual(filtered_response.status_code, 200)
        filtered = filtered_response.json()
        self.assertEqual(filtered["messages"][-1]["content"], "Réponse finale")
        self.assertNotIn("think", filtered_response.text.lower())
        self.assertNotIn("secret", filtered_response.text.lower())

        failed_response = self.send("Deuxième question", filtered)
        self.assertEqual(failed_response.status_code, 502)
        failed = failed_response.json()["conversation"]
        self.assertEqual(failed["messages"][-1]["role"], "user")
        self.assertEqual(failed["messages"][-1]["status"], "failed")
        with closing(sqlite3.connect(self.database_path)) as connection:
            all_content = " ".join(row[0] for row in connection.execute("SELECT content FROM messages"))
        self.assertNotIn("<think", all_content.lower())
        self.assertNotIn("</think", all_content.lower())
        self.assertNotIn("secret", all_content.lower())


class ConcurrentApiTests(unittest.TestCase):
    def test_only_one_generation_is_accepted_for_a_conversation(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-concurrent-test-", dir=Path(__file__).resolve().parent
        )
        try:
            database_path = Path(temporary_directory.name) / "concurrent.sqlite3"
            gateway = BlockingModelGateway()
            application = create_app(database_path, gateway)
            with TestClient(application) as client, ThreadPoolExecutor(max_workers=1) as pool:
                first_future = pool.submit(
                    client.post,
                    "/api/conversations/messages",
                    json={
                        "conversation_id": None,
                        "message": "Première question",
                        "expected_revision": None,
                    },
                )
                self.assertTrue(gateway.started.wait(5))
                database = application.state.database
                pending = database.list_conversations()[0]
                second = client.post(
                    "/api/conversations/messages",
                    json={
                        "conversation_id": pending["id"],
                        "message": "Envoi concurrent",
                        "expected_revision": pending["revision"],
                    },
                )
                self.assertEqual(second.status_code, 409)
                gateway.release.set()
                first = first_future.result(timeout=10)
                self.assertEqual(first.status_code, 200)
                self.assertEqual(gateway.calls, 1)
                self.assertEqual(database.count_messages(pending["id"]), 2)
        finally:
            temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()

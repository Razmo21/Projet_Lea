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
from app.database import (  # noqa: E402
    MEMORY_DUPLICATE_CONFIRMATION,
    MEMORY_FORGOTTEN_CONFIRMATION,
    MEMORY_NOT_FOUND_CONFIRMATION,
    MEMORY_REMEMBERED_CONFIRMATION,
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

    def test_literal_no_think_user_text_is_preserved_as_user_data(self) -> None:
        response = self.send("Que signifie le texte /no_think ?")

        self.assertEqual(response.status_code, 200)
        conversation = response.json()
        self.assertEqual(
            conversation["messages"][0]["content"],
            "Que signifie le texte /no_think ?",
        )
        with closing(sqlite3.connect(self.database_path)) as connection:
            stored = connection.execute(
                "SELECT content FROM messages WHERE role = 'user'"
            ).fetchone()[0]
        self.assertEqual(stored, "Que signifie le texte /no_think ?")

    def test_memory_remember_duplicate_forget_and_miss_never_call_model(self) -> None:
        remembered_response = self.send("Retiens que je m'appelle Stan.")

        self.assertEqual(remembered_response.status_code, 200)
        remembered = remembered_response.json()
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(
            [message["content"] for message in remembered["messages"]],
            ["Retiens que je m'appelle Stan.", MEMORY_REMEMBERED_CONFIRMATION],
        )
        self.assertEqual(
            [message["kind"] for message in remembered["messages"]],
            ["memory", "memory"],
        )

        duplicated_response = self.send(
            "  RETIENS   que je m’appelle Stan !  ", remembered
        )
        self.assertEqual(duplicated_response.status_code, 200)
        duplicated = duplicated_response.json()
        self.assertEqual(duplicated["messages"][-1]["content"], MEMORY_DUPLICATE_CONFIRMATION)
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(len(self.application.state.database.list_memories()), 1)

        missed_response = self.send("Oublie que mon prénom est Stan.", duplicated)
        self.assertEqual(missed_response.status_code, 200)
        missed = missed_response.json()
        self.assertEqual(missed["messages"][-1]["content"], MEMORY_NOT_FOUND_CONFIRMATION)
        self.assertEqual(len(self.application.state.database.list_memories()), 1)
        self.assertEqual(self.gateway.calls, [])

        forgotten_response = self.send("Oublie que je m’appelle Stan", missed)
        self.assertEqual(forgotten_response.status_code, 200)
        forgotten = forgotten_response.json()
        self.assertEqual(forgotten["messages"][-1]["content"], MEMORY_FORGOTTEN_CONFIRMATION)
        self.assertEqual(self.application.state.database.list_memories(), [])
        self.assertEqual(self.gateway.calls, [])

    def test_empty_memory_commands_are_422_and_do_not_write(self) -> None:
        for command in (
            "Retiens que",
            "Souviens-toi que",
            "Mémorise que...",
            "Oublie que ?!",
        ):
            with self.subTest(command=command):
                response = self.send(command)
                self.assertEqual(response.status_code, 422)

        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(self.application.state.database.list_conversations(), [])
        self.assertEqual(self.application.state.database.list_memories(), [])

    def test_ordinary_fact_is_not_automatically_memorized(self) -> None:
        response = self.send("Je m'appelle Stan.")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.gateway.calls), 1)
        self.assertEqual(self.application.state.database.list_memories(), [])
        self.assertEqual(
            [message["kind"] for message in response.json()["messages"]],
            ["conversation", "conversation"],
        )

    def test_memory_survives_source_deletion_and_backend_restart(self) -> None:
        source = self.send("Souviens-toi que mon chien s'appelle Rex.").json()
        deleted = self.client.request(
            "DELETE",
            f"/api/conversations/{source['id']}",
            json={"expected_revision": source["revision"]},
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(len(self.application.state.database.list_memories()), 1)

        restarted_application = create_app(self.database_path, FakeModelGateway())
        with TestClient(restarted_application):
            memories = restarted_application.state.database.list_memories()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["normalized_content"], "mon chien s'appelle rex")

    def test_stale_revision_cannot_change_memory(self) -> None:
        conversation = self.send("Question normale").json()
        renamed = self.client.patch(
            f"/api/conversations/{conversation['id']}",
            json={"title": "Version récente", "expected_revision": conversation["revision"]},
        ).json()

        stale = self.client.post(
            "/api/conversations/messages",
            json={
                "conversation_id": conversation["id"],
                "message": "Retiens que je m'appelle Stan.",
                "expected_revision": conversation["revision"],
            },
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.application.state.database.list_memories(), [])
        current = self.application.state.database.get_conversation(conversation["id"])
        self.assertEqual(current["revision"], renamed["revision"])
        self.assertEqual(len(current["messages"]), 2)

    def test_memory_turns_cannot_be_edited_regenerated_or_retried(self) -> None:
        conversation = self.send("Retiens que je m'appelle Stan.").json()
        user, assistant = conversation["messages"]

        edited = self.client.patch(
            f"/api/conversations/{conversation['id']}/messages/{user['id']}",
            json={"content": "Retiens que je m'appelle Bob.", "expected_revision": conversation["revision"]},
        )
        regenerated = self.client.post(
            f"/api/conversations/{conversation['id']}/messages/{assistant['id']}/regenerate",
            json={"expected_revision": conversation["revision"]},
        )
        retried = self.client.post(
            f"/api/conversations/{conversation['id']}/messages/{user['id']}/retry",
            json={"expected_revision": conversation["revision"]},
        )

        self.assertEqual(edited.status_code, 400)
        self.assertEqual(regenerated.status_code, 400)
        self.assertEqual(retried.status_code, 400)
        self.assertEqual(self.application.state.database.get_conversation(conversation["id"]), conversation)
        self.assertEqual(len(self.application.state.database.list_memories()), 1)
        self.assertEqual(self.gateway.calls, [])

    def test_normal_message_cannot_be_edited_into_a_memory_command(self) -> None:
        conversation = self.send("Question normale").json()
        user = conversation["messages"][0]
        calls_before = len(self.gateway.calls)

        response = self.client.patch(
            f"/api/conversations/{conversation['id']}/messages/{user['id']}",
            json={
                "content": "Retiens que je m'appelle Stan.",
                "expected_revision": conversation["revision"],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.gateway.calls), calls_before)
        self.assertEqual(self.application.state.database.list_memories(), [])

    def test_model_payload_uses_memory_but_excludes_memory_management_turns(self) -> None:
        memory_conversation = self.send("Retiens que je m'appelle Stan.").json()
        normal_response = self.send("Comment je m'appelle ?", memory_conversation)

        self.assertEqual(normal_response.status_code, 200)
        self.assertEqual(len(self.gateway.calls), 1)
        remembered_payload = self.gateway.calls[-1]
        serialized = str(remembered_payload)
        self.assertNotIn("Retiens que", serialized)
        self.assertNotIn(MEMORY_REMEMBERED_CONFIRMATION, serialized)
        self.assertEqual(serialized.count("Stan"), 1)
        self.assertIn("faits_explicites", remembered_payload[-1]["content"])

        forgotten = self.send(
            "Oublie que je m'appelle Stan.", normal_response.json()
        )
        self.assertEqual(forgotten.status_code, 200)
        calls_before = len(self.gateway.calls)
        after_forget = self.send(
            "Quel prénom est enregistré en mémoire générale ?",
            forgotten.json(),
        )

        self.assertEqual(after_forget.status_code, 200)
        self.assertEqual(len(self.gateway.calls), calls_before + 1)
        forgotten_payload = str(self.gateway.calls[-1])
        self.assertNotIn("Stan", forgotten_payload)
        self.assertNotIn("Retiens que", forgotten_payload)
        self.assertNotIn("Oublie que", forgotten_payload)
        self.assertNotIn(MEMORY_REMEMBERED_CONFIRMATION, forgotten_payload)
        self.assertNotIn(MEMORY_FORGOTTEN_CONFIRMATION, forgotten_payload)

    def test_regeneration_budget_refusal_preserves_the_existing_answer(self) -> None:
        self.gateway.responses = ["Réponse longue existante"]
        conversation = self.send("q" * 5900).json()
        remembered = self.send("Retiens que " + "m" * 700 + ".")
        self.assertEqual(remembered.status_code, 200)
        calls_before = len(self.gateway.calls)

        response = self.client.post(
            f"/api/conversations/{conversation['id']}/messages/"
            f"{conversation['messages'][1]['id']}/regenerate",
            json={"expected_revision": conversation["revision"]},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("fenêtre de contexte", response.json()["detail"])
        self.assertEqual(len(self.gateway.calls), calls_before)
        self.assertEqual(
            self.application.state.database.get_conversation(conversation["id"]),
            conversation,
        )

        edited = self.client.patch(
            f"/api/conversations/{conversation['id']}/messages/"
            f"{conversation['messages'][0]['id']}",
            json={
                "content": "e" * 5900,
                "expected_revision": conversation["revision"],
            },
        )
        self.assertEqual(edited.status_code, 422)
        self.assertEqual(len(self.gateway.calls), calls_before)
        self.assertEqual(
            self.application.state.database.get_conversation(conversation["id"]),
            conversation,
        )

    def test_memory_and_large_question_are_rejected_before_any_pending_write(self) -> None:
        remembered = self.send("Retiens que " + "m" * 700 + ".")
        self.assertEqual(remembered.status_code, 200)
        conversations_before = self.application.state.database.list_conversations()
        calls_before = len(self.gateway.calls)

        response = self.send("q" * 5800)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.gateway.calls), calls_before)
        self.assertEqual(
            self.application.state.database.list_conversations(),
            conversations_before,
        )
        self.assertEqual(len(self.application.state.database.list_memories()), 1)

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

    def test_concurrent_memory_commands_create_one_exact_memory(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory(
            prefix="lea-memory-concurrent-test-", dir=Path(__file__).resolve().parent
        )
        try:
            database_path = Path(temporary_directory.name) / "concurrent-memory.sqlite3"
            gateway = FakeModelGateway()
            application = create_app(database_path, gateway)
            with TestClient(application) as client, ThreadPoolExecutor(max_workers=2) as pool:
                barrier = threading.Barrier(2)

                def remember() -> object:
                    barrier.wait(5)
                    return client.post(
                        "/api/conversations/messages",
                        json={
                            "conversation_id": None,
                            "message": "Retiens que je m'appelle Stan.",
                            "expected_revision": None,
                        },
                    )

                responses = [future.result(timeout=10) for future in (
                    pool.submit(remember),
                    pool.submit(remember),
                )]

            self.assertEqual([response.status_code for response in responses], [200, 200])
            confirmations = {
                response.json()["messages"][-1]["content"] for response in responses
            }
            self.assertEqual(
                confirmations,
                {MEMORY_REMEMBERED_CONFIRMATION, MEMORY_DUPLICATE_CONFIRMATION},
            )
            self.assertEqual(len(application.state.database.list_memories()), 1)
            self.assertEqual(gateway.calls, [])
        finally:
            temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()

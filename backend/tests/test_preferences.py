"""Persistance des préférences sans modèle, serveur ni donnée utilisateur réelle."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Database  # noqa: E402
from app.preferences import (  # noqa: E402
    PreferenceChange, PreferencesConflict, PreferencesError, PreferencesStore,
)


class PreferencesTests(unittest.TestCase):
    """Vérifie l'autorité SQLite, les révisions et les erreurs sans fallback trompeur."""

    def setUp(self) -> None:
        """Isole chaque essai, y compris les utilitaires lancés en sous-processus."""

        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "backend/tests")
        self.path = Path(self.temporary.name) / "preferences.sqlite3"
        self.database = Database(self.path)
        self.database.initialize(recover_generations=False)
        self.store = PreferencesStore(self.database)

    def tearDown(self) -> None:
        """Retire uniquement les fichiers de cet essai."""

        self.temporary.cleanup()

    def change(self, level: str, revision: int = 0) -> PreferenceChange:
        """Construit le même contrat strict que le pont local."""

        return PreferenceChange.model_validate({"general_reasoning": level, "expected_revision": revision})

    def cli(self, action: str, payload: str = "", **environment: str) -> dict:
        """Utilise le vrai utilitaire avec un chemin de base contrôlé par l'environnement."""

        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/preferences.py"), action],
            input=payload, text=True, capture_output=True, check=True,
            env={**os.environ, "LEA_DB_PATH": str(self.path), **environment}, cwd=ROOT,
        )
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_defaults_save_and_restart(self) -> None:
        """Une nouvelle base commence en Low et le prochain composant retrouve High."""

        self.assertEqual(self.store.read().general_reasoning, "low")
        self.assertEqual(self.store.save(self.change("high")).revision, 1)
        reopened = Database(self.path)
        reopened.initialize(recover_generations=False)
        self.assertEqual(PreferencesStore(reopened).read().general_reasoning, "high")
        self.assertEqual(self.store.save(self.change("low", 1)).revision, 2)

    def test_invalid_values_types_and_extra_fields_are_refused(self) -> None:
        """Aucune valeur libre, conversion implicite, chemin ou commande n'est acceptée."""

        for payload in (
            {"general_reasoning": "ultra", "expected_revision": 0},
            {"general_reasoning": True, "expected_revision": 0},
            {"general_reasoning": "high", "expected_revision": True},
            {"general_reasoning": "high", "expected_revision": "0"},
            {"general_reasoning": "high", "expected_revision": 0, "path": "C:/Windows"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                PreferenceChange.model_validate(payload)
        self.assertEqual(self.store.read().revision, 0)

    def test_stale_revision_and_concurrent_writers(self) -> None:
        """Le verrou transactionnel garantit un seul gagnant entre deux onglets."""

        def save() -> bool:
            """Retourne seulement si cette écriture a remporté la révision attendue."""

            try:
                self.store.save(self.change("high"))
                return True
            except PreferencesConflict:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(lambda _: save(), range(2))), [False, True])
        self.assertEqual(self.store.read().revision, 1)

    def test_write_failure_keeps_last_valid_value(self) -> None:
        """Un refus SQLite réel annule la transaction et ne confirme pas la sauvegarde."""

        self.store.save(self.change("high"))
        with self.database.connection() as connection:
            connection.execute(
                "CREATE TRIGGER deny_preference_write BEFORE UPDATE ON user_preferences "
                "BEGIN SELECT RAISE(ABORT, 'test write denied'); END"
            )
        with self.assertRaises(PreferencesError):
            self.store.save(self.change("low", 1))
        self.assertEqual(self.store.read().general_reasoning, "high")
        self.assertEqual(self.store.read().revision, 1)

    def test_corrupt_preferences_are_not_overwritten(self) -> None:
        """Une donnée altérée est signalée, sans réinitialisation silencieuse."""

        with self.database.connection() as connection:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            connection.execute("UPDATE user_preferences SET general_reasoning = 'invalid'")
        with self.assertRaises(PreferencesError):
            self.store.read()
        self.assertEqual(self.cli("read")["status"], 503)

    def test_cli_never_recovers_an_active_generation_or_changes_registry(self) -> None:
        """Ouvrir les paramètres pendant une réponse ne marque pas celle-ci comme interrompue."""

        registry = (ROOT / "config/models.json").read_bytes()
        conversation_id, _ = self.database.create_pending_conversation("Question active")
        before = self.database.get_conversation(conversation_id)
        result = self.cli("save", json.dumps({"general_reasoning": "high", "expected_revision": 0}))
        self.assertEqual(result["status"], 200)
        self.assertEqual(self.database.get_conversation(conversation_id), before)
        self.assertEqual((ROOT / "config/models.json").read_bytes(), registry)

    def test_cli_errors_are_safe_and_strict(self) -> None:
        """Le pont refuse JSON malformé et valeurs libres avant toute modification."""

        for payload in ("{", "{}", "x" * 1025, '{"command":"whoami"}'):
            self.assertEqual(self.cli("save", payload)["status"], 422)
        self.assertEqual(self.cli("read")["body"]["revision"], 0)

    def test_localized_future_column_is_preserved(self) -> None:
        """Une colonne ajoutée par une future migration n'est pas écrasée par ce réglage."""

        with self.database.connection() as connection:
            connection.execute("ALTER TABLE user_preferences ADD COLUMN isolated_test_setting TEXT DEFAULT 'kept'")
        self.store.save(self.change("high"))
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT isolated_test_setting FROM user_preferences").fetchone()[0], "kept")

    def test_absent_database_and_missing_preferences_row(self) -> None:
        """Une base absente reçoit Low ; une ligne perdue n'est pas réinventée."""

        absent = str(Path(self.temporary.name) / "absent.sqlite3")
        self.assertEqual(self.cli("read", LEA_DB_PATH=absent)["body"]["general_reasoning"], "low")
        with self.database.connection() as connection:
            connection.execute("DELETE FROM user_preferences")
        self.assertEqual(self.cli("read")["status"], 503)
        self.assertEqual(self.cli("save", '{"general_reasoning":"high","expected_revision":0}')["status"], 503)

    def test_unsupported_or_invalid_registry_does_not_save(self) -> None:
        """Une substitution sans capacité ne propose pas un contrôle sans effet."""

        registry = json.loads((ROOT / "config/models.json").read_text(encoding="utf-8"))
        general_id = next(profile["model_id"] for profile in registry["profiles"] if profile["id"] == "general")
        next(model for model in registry["models"] if model["id"] == general_id)["reasoning_control"] = "none"
        path = Path(self.temporary.name) / "models.json"
        path.write_text(json.dumps(registry), encoding="utf-8")
        environment = {"LEA_MODEL_REGISTRY": str(path)}
        result = self.cli("read", **environment)
        self.assertEqual(result["status"], 200)
        self.assertFalse(result["body"]["general_reasoning_available"])
        self.assertEqual(self.cli("save", '{"general_reasoning":"high","expected_revision":0}', **environment)["status"], 503)
        self.assertEqual(self.store.read().revision, 0)
        path.write_text("invalid", encoding="utf-8")
        self.assertEqual(self.cli("read", **environment)["status"], 503)

    def test_corrupt_database_is_not_replaced(self) -> None:
        """Un fichier SQLite illisible produit une erreur sans écrasement destructif."""

        path = Path(self.temporary.name) / "corrupt.sqlite3"
        original = b"not a SQLite database"
        path.write_bytes(original)
        self.assertEqual(self.cli("read", LEA_DB_PATH=str(path))["status"], 503)
        self.assertEqual(path.read_bytes(), original)

    def test_migration_from_stage11_preserves_conversations(self) -> None:
        """La migration additive ne reconstruit ni messages ni souvenirs existants."""

        conversation_id, _ = self.database.create_pending_conversation("Ancienne conversation")
        before = self.database.get_conversation(conversation_id)
        with self.database.connection() as connection:
            connection.execute("DROP TABLE user_preferences")
            connection.execute("DELETE FROM schema_migrations WHERE version = 8")
        self.database.initialize(recover_generations=False)
        self.assertEqual(self.database.get_conversation(conversation_id), before)
        self.assertEqual(self.store.read().general_reasoning, "low")


if __name__ == "__main__":
    unittest.main()

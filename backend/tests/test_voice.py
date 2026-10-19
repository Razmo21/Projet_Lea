"""Offline contracts and persistence: no model, microphone or user database required."""

import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from pydantic import ValidationError
from app.database import Database, ConversationOperationError, RevisionConflictError
from app.migrations import MIGRATIONS, apply_migrations
from app.model_registry import VoiceFile, load_model_registry
from app.preferences import PreferenceChange, PreferencesStore
from app.voice import VoiceError, asset_path, speech_text, synthesize, transcribe, validate_wav, voice_status


def wav(seconds=1, rate=16000, channels=1, silent=False):
    """Build a deterministic PCM fixture, not a physical microphone recording."""
    target = io.BytesIO()
    with wave.open(target, "wb") as stream:
        stream.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        stream.writeframes((b"\x00\x00" if silent else b"\x00\x20") * int(seconds * rate * channels))
    return target.getvalue()


class VoiceTests(unittest.TestCase):
    """Reject malformed audio, unknown settings, paths and hidden reasoning."""

    def test_pcm_contract(self):
        """Only complete bounded mono PCM16 audio reaches STT."""
        self.assertEqual(validate_wav(wav()), 1)
        for value in (b"", b"not audio", wav(silent=True), wav(seconds=.1), wav(seconds=121), wav(rate=22050), wav(channels=2), wav()[:-10]):
            with self.subTest(size=len(value)), self.assertRaises(VoiceError):
                validate_wav(value)

    def test_invalid_browser_payload_never_launches_whisper(self):
        """The transport requires converted WAV, not a renamed container or truncated PCM."""
        registry = load_model_registry()
        with patch('app.voice.subprocess.run') as run:
            for value in (b'\x1a\x45\xdf\xa3' + b'\x00' * 100, b'\x00\x00\x00\x18ftyp' + b'\x00' * 100, wav()[:-32]):
                with self.subTest(size=len(value)), self.assertRaises(VoiceError):
                    transcribe(registry, value, 'fr')
            run.assert_not_called()

    def test_text_preparation_is_honest(self):
        """Technical omissions are announced without changing the stored response."""
        original = "# Résultat\n**Validé**. [Détails](https://invalid.example)\n```python\nsecret = 1\n```"
        clean, partial = speech_text(original)
        self.assertTrue(partial)
        self.assertNotIn("secret", clean)
        self.assertNotIn("https", clean)
        self.assertIn("Lecture partielle", clean)
        self.assertIn("Validé", clean)
        self.assertEqual(speech_text("Bonjour, Léa !"), ("Bonjour, Léa !", False))
        for value in ("", "<think>privé</think>Bonjour", "A /no_think", "x" * 32001):
            with self.assertRaises(VoiceError): speech_text(value)
        self.assertTrue(speech_text("Mot " * 2000)[1])

    def test_registry_confines_assets(self):
        """A browser pathname cannot become a model or executable argument."""
        registry = load_model_registry()
        for path in ("../file", "C:/Windows/file", "//host/file"):
            with self.assertRaises(ValidationError): VoiceFile(path=path, sha256="0" * 64)
        with self.assertRaises(VoiceError): asset_path(registry, VoiceFile(path="backend/file", sha256="0" * 64))

    def test_transcription_subprocess_is_cpu_bounded_and_uses_pipes(self):
        """Simulate the engine only; arguments, timeout and audio contract stay real."""
        registry = load_model_registry()
        with patch('app.voice.asset_path', return_value=Path('local-file')), patch('app.voice.subprocess.run') as run:
            run.return_value.returncode = 0; run.return_value.stdout = "Bonjour Léa".encode(); run.return_value.stderr = b''
            result = transcribe(registry, wav(), "fr")
            self.assertEqual(result['text'], 'Bonjour Léa')
            self.assertIn('-ng', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['input'], wav())
            self.assertEqual(run.call_args.kwargs['timeout'], 180)
            run.return_value.returncode = 1
            with self.assertRaises(VoiceError): transcribe(registry, wav(), "fr")
        with self.assertRaises(VoiceError): transcribe(registry, wav(), 'auto')

    def test_invalid_voice_preferences(self):
        """Strict types and ranges prevent silent clamping or invented controls."""
        for key, value in (("voice_volume", -1), ("voice_volume", True), ("voice_rate", 2), ("voice_rate", float('nan')), ("voice_enabled", 1), ("voice_language", "auto"), ("voice_id", ""), ("voice_id", "../voice"), ("voice_microphone_id", "x" * 257)):
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                PreferenceChange.model_validate({"expected_revision": 0, key: value})

    def test_two_tts_engines_are_independent_and_rate_support_is_truthful(self):
        """The natural voice is first, while SIWIS remains selectable and rate-aware."""
        registry = load_model_registry()
        status = voice_status(registry)
        self.assertEqual(
            [(voice["id"], voice["label"], voice["engine"], voice["supports_rate"]) for voice in status["voices"]],
            [
                ("lea_voice", "Léa — Voix naturelle française", "pocket-tts", False),
                ("fr-siwis", "SIWIS — Voix classique", "piper", True),
            ],
        )
        self.assertEqual(status["tts_engines"], ["piper", "pocket-tts"])
        with self.assertRaisesRegex(VoiceError, "vitesse est fixe"):
            synthesize(registry, "Bonjour", "lea_voice", 1.2)
        with self.assertRaisesRegex(VoiceError, "sélectionnée"):
            synthesize(registry, "Bonjour", "unknown", 1)

    def test_tts_dispatch_never_falls_back_to_another_voice(self):
        """Each identifier reaches only its configured adapter and preserves its rate."""
        registry = load_model_registry()
        natural = {"audio": b"natural"}
        classic = {"audio": b"classic"}
        with patch("app.voice._synthesize_pocket_tts", return_value=natural) as pocket, patch(
            "app.voice._synthesize_piper", return_value=classic
        ) as piper:
            self.assertIs(synthesize(registry, "Bonjour", "lea_voice", 1), natural)
            pocket.assert_called_once()
            piper.assert_not_called()
            self.assertIs(synthesize(registry, "Bonjour", "fr-siwis", 1.25), classic)
            piper.assert_called_once()


class VoiceHistoryTests(unittest.TestCase):
    """The normal database owns vocal turns, including interrupted OpenHands runs."""

    def setUp(self):
        """Keep all disposable files inside a fresh test directory."""
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'backend/tests')
        self.db = Database(Path(self.temp.name) / 'voice.sqlite3')
        self.db.initialize()

    def tearDown(self):
        """Remove only this fixture, never user conversations or checkpoints."""
        self.temp.cleanup()

    def run_record(self, **kwargs):
        """Persist a simulated run with the same transaction as the real manager."""
        return self.db.create_agent_run(str(uuid4()), str(uuid4()), 'development', 'Lire le projet', record_conversation=True, **kwargs)

    def test_agent_pair_is_atomic_idempotent_and_not_chat_context(self):
        """Terminal updates change the existing assistant message exactly once."""
        run = self.run_record()
        cid = run['conversation_id']
        before = self.db.get_conversation(cid)
        self.assertTrue(before['generation_active'])
        self.assertEqual(len(before['messages']), 2)
        self.db.update_agent_run(run['run_id'], state='completed', validation_status='validated', result_summary='Test vert.')
        after = self.db.get_conversation(cid)
        self.assertFalse(after['generation_active'])
        self.assertIn('validated', after['messages'][-1]['content'])
        self.db.update_agent_run(run['run_id'], result_summary='Test vert.')
        self.assertEqual(self.db.get_conversation(cid), after)
        mid = self.db.add_pending_message(cid, 'Bonjour', after['revision'])
        history, _ = self.db.completed_history_before(cid, mid)
        self.assertEqual(history, [])

    def test_agent_turn_cannot_be_replayed_as_chat(self):
        """Retry/edit/regenerate never bypass the OpenHands contract."""
        run = self.run_record()
        self.db.update_agent_run(run['run_id'], state='failed', result_summary='Validation échouée.')
        detail = self.db.get_conversation(run['conversation_id'])
        cid, revision = detail['id'], detail['revision']
        user, assistant = detail['messages']
        for operation in (
            lambda: self.db.retry_message(cid, user['id'], revision),
            lambda: self.db.edit_user_message(cid, user['id'], 'Autre tâche', revision),
            lambda: self.db.regenerate_assistant_message(cid, assistant['id'], revision),
        ):
            with self.assertRaises(ConversationOperationError): operation()

    def test_recovery_keeps_nonterminal_run_until_verified_stop(self):
        """A restart does not convert uncertain Docker ownership into a finished turn."""
        run = self.run_record()
        self.db.initialize()
        self.assertTrue(self.db.get_conversation(run['conversation_id'])['generation_active'])
        self.db.update_agent_run(run['run_id'], state='failed', result_summary='Arrêt vérifié.')
        self.assertFalse(self.db.get_conversation(run['conversation_id'])['generation_active'])

    def test_stale_revision_creates_neither_run_nor_pair(self):
        """An obsolete tab cannot append a voice task to changed history."""
        run = self.run_record()
        self.db.update_agent_run(run['run_id'], state='cancelled')
        before = self.db.get_conversation(run['conversation_id'])
        with self.assertRaises(RevisionConflictError): self.run_record(conversation_id=before['id'], expected_revision=0)
        self.assertEqual(self.db.get_conversation(before['id']), before)
        self.assertEqual(len(self.db.list_agent_runs()), 1)

    def test_preferences_survive_restart_and_partial_changes(self):
        """Voice changes neither reset Low/High nor the optional resource diagram."""
        store = PreferencesStore(self.db)
        store.save(PreferenceChange(expected_revision=0, general_reasoning='high', show_resource_chart=True))
        store.save(PreferenceChange(expected_revision=1, voice_language='en', voice_enabled=False, voice_volume=.4, voice_rate=1.2, voice_microphone_id='device'))
        self.db.initialize(recover_generations=False)
        value = store.read()
        self.assertEqual((value.general_reasoning, value.show_resource_chart, value.voice_language, value.voice_volume), ('high', True, 'en', .4))

    def test_stage14_voice_migration_preserves_other_settings(self):
        """Apply v10/v11 to a genuine v9 database and select Léa without other resets."""
        path = Path(self.temp.name) / 'v9.sqlite3'
        with sqlite3.connect(path) as connection:
            apply_migrations(connection, {key: value for key, value in MIGRATIONS.items() if key <= 9})
            connection.execute("UPDATE user_preferences SET general_reasoning='high', revision=7, show_resource_chart=1")
        connection.close()
        old = Database(path); old.initialize(recover_generations=False)
        value = PreferencesStore(old).read()
        self.assertEqual(
            (value.revision, value.general_reasoning, value.show_resource_chart, value.voice_language, value.voice_id),
            (7, 'high', True, 'fr', 'lea_voice'),
        )


if __name__ == '__main__':
    unittest.main()

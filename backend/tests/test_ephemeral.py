"""Confidentialité du chat RAM, sans données utilisateur ni modèle réel."""

import asyncio
from pathlib import Path
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
import httpx
from contextlib import closing
from unittest.mock import patch

from fastapi.testclient import TestClient

from test_api import FakeModelGateway, FakeModelController, create_app
from test_web_gateway import RecordingProvider, public_resolver
from app.preferences import PreferenceChange
from app.web_gateway import SafeHttpFetcher


class EphemeralTests(unittest.TestCase):
    """Les preuves portent sur les écritures et appels réels du backend de test."""

    def setUp(self):
        """Isole la base et utilise la même application que les conversations normales."""
        self.directory = tempfile.TemporaryDirectory(prefix="lea-ephemeral-", dir=Path(__file__).parent)
        self.path = Path(self.directory.name) / "test.sqlite3"
        self.gateway = FakeModelGateway()
        self.app = create_app(self.path, self.gateway, model_controller=FakeModelController())
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()

    def tearDown(self):
        """La fermeture doit aussi vider toutes les sessions et annuler leurs délais."""
        self.context.__exit__(None, None, None)
        self.assertEqual(self.app.state.ephemeral.sessions, {})
        self.directory.cleanup()

    def open(self):
        """Ouvre une session indépendante et vérifie les en-têtes de confidentialité."""
        response = self.client.post('/api/ephemeral')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        return response.json()

    def send(self, session, text):
        """Envoie uniquement un texte et la révision, jamais un historique navigateur."""
        return self.client.post(f"/api/ephemeral/{session['id']}/messages", json={
            'message': text, 'expected_revision': session['revision'],
        })

    def snapshot(self):
        """Compare toutes les tables, y compris mémoire, sources et runs."""
        with closing(sqlite3.connect(self.path)) as connection:
            return '\n'.join(connection.iterdump())

    def test_turns_use_only_session_context_and_never_write_sqlite(self):
        """Un souvenir et une conversation normale ne doivent pas entrer dans le prompt privé."""
        self.client.post('/api/conversations/messages', json={'message': 'Retiens que mon animal se nomme SecretNormal.'})
        self.gateway.calls.clear()
        before = self.snapshot()
        with patch.object(self.app.state.database, 'list_memories', side_effect=AssertionError('memory read')), \
             patch.object(self.app.state.database, 'complete_generation', side_effect=AssertionError('persistent write')):
            session = self.open()
            first = self.send(session, 'Mon code temporaire est BRUME-823.').json()
            second = self.send(first, 'Quel est ce code ?')
            self.assertEqual(second.status_code, 200, second.text)
            self.assertIn('BRUME-823', str(self.gateway.calls[-1]))
            self.assertNotIn('SecretNormal', str(self.gateway.calls))
            self.assertEqual(len(second.json()['messages']), 4)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.client.get(f"/api/conversations/{session['id']}").status_code, 404)

    def test_memory_and_web_never_reach_tools_or_model(self):
        """Même une autorisation Web explicite ou une commande mémoire reste sans effet persistant."""
        session = self.open()
        before = self.snapshot()
        with patch.object(self.app.state.ephemeral_web_gateway, 'retrieve', side_effect=AssertionError('network')):
            for text in ('Retiens que mon code est AZUR.', 'Oublie que mon code est AZUR.',
                         'Cherche sur Internet les nouvelles.', 'Quel temps fait-il actuellement à Québec ?'):
                result = self.send(session, text)
                self.assertEqual(result.status_code, 200, result.text)
                session = result.json()
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual(before, self.snapshot())

    def test_close_restart_and_other_sessions_cannot_recover_text(self):
        """Le jeton n'est jamais récupéré depuis SQLite ni partagé entre sessions."""
        session = self.send(self.open(), 'Texte privé unique.').json()
        other = self.open()
        self.send(other, 'Bonjour')
        self.assertNotIn('Texte privé unique', str(self.gateway.calls[-1]))
        self.assertEqual(self.client.delete(f"/api/ephemeral/{session['id']}").status_code, 204)
        self.assertEqual(self.send(session, 'Suite').status_code, 410)
        restarted = create_app(self.path, FakeModelGateway(), model_controller=FakeModelController())
        with TestClient(restarted) as client:
            self.assertNotEqual(client.get('/api/models/status').json()['instance_id'], other['instance_id'])
            self.assertEqual(client.post(f"/api/ephemeral/{other['id']}/messages", json={
                'message': 'Suite', 'expected_revision': 0,
            }).status_code, 410)

    def test_origin_fields_revision_and_profile_guards(self):
        """Les anciennes routes et les profils agentiques ne deviennent pas des portes d'entrée."""
        self.assertEqual(self.client.post('/api/ephemeral', headers={'Origin': 'https://evil.example'}).status_code, 403)
        session = self.open()
        for extra in ({'web_request_id': session['id']}, {'history': []}, {'conversation_id': session['id']}):
            response = self.client.post(f"/api/ephemeral/{session['id']}/messages", json={
                'message': 'Bonjour', 'expected_revision': 0, **extra,
            })
            self.assertEqual(response.status_code, 422)
        updated = self.send(session, 'Bonjour').json()
        self.assertEqual(self.send(session, 'Ancienne révision').status_code, 409)
        self.app.state.runtime_coordinator.active_profile_id = 'development'
        self.assertEqual(self.client.post('/api/ephemeral').status_code, 409)
        self.assertEqual(self.send(updated, 'Suite').status_code, 409)
        self.assertEqual(self.app.state.runtime_coordinator.active_generations, 0)

    def test_model_failure_citations_and_current_information_guards(self):
        """Un échec ne persiste rien et ne bloque pas le prochain envoi ; les faux outils restent refusés."""
        session = self.open()
        self.gateway.responses = [RuntimeError('SECRET INTERNE'), 'Donnée inventée [S999].', 'Réponse valide.']
        failure = self.send(session, 'Question générale')
        self.assertEqual(failure.status_code, 502)
        self.assertNotIn('SECRET INTERNE', failure.text)
        result = self.send(session, 'Question générale')
        self.assertNotIn('[S999]', result.text)
        self.assertEqual(self.app.state.database.list_conversations(), [])
        self.assertEqual(self.app.state.runtime_coordinator.active_generations, 0)

    def test_veterinary_is_not_allowed_in_temporary_mode(self):
        """Le périmètre demandé est Général seulement, sans modifier les autres profils."""
        self.app.state.runtime_coordinator.active_profile_id = 'veterinary'
        self.assertEqual(self.client.post('/api/ephemeral').status_code, 409)

    def test_close_cancels_generation_and_releases_runtime(self):
        """La fermeture réelle de l'endpoint annule l'inférence et libère le verrou global."""
        started = threading.Event()
        cancelled = threading.Event()

        async def wait_for_close(_messages):
            """Attend sans bloquer la boucle afin que DELETE puisse annuler le tour."""
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return 'Ne doit pas arriver'

        self.gateway.generate = wait_for_close
        session = self.open()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.send, session, 'Texte privé à annuler')
            self.assertTrue(started.wait(3))
            self.assertEqual(self.client.delete(f"/api/ephemeral/{session['id']}").status_code, 204)
            self.assertEqual(pending.result(timeout=5).status_code, 409)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.app.state.runtime_coordinator.active_generations, 0)
        self.assertEqual(self.app.state.database.list_conversations(), [])
        self.assertEqual(self.app.state.ephemeral.sessions, {})

    def test_web_consent_sources_and_no_history_in_outbound_query(self):
        """Vrai chemin HTTP du Gateway sur transport simulé : zéro réseau avant accord, sources réelles ensuite."""
        self.app.state.preferences.save(PreferenceChange(expected_revision=0, web_enabled=True))
        web = self.app.state.ephemeral_web_gateway
        provider = RecordingProvider()
        calls = []

        def transport(request):
            """Livre une source connue et compte réellement les accès HTTP."""
            calls.append(str(request.url))
            return httpx.Response(200, headers={'content-type': 'text/html'},
                                  content=b'<html><title>Document public</title><p>Fait public fiable. '
                                  b'Voici un document accessible contenant une explication publique et son contexte.</p></html>')

        web.provider = provider
        web.fetcher = SafeHttpFetcher(resolver=public_resolver, transport=httpx.MockTransport(transport))
        self.assertIsNone(web.dynamic_reader)
        session = self.open()
        session = self.send(session, 'Mon secret temporaire est BRUME-823.').json()
        session = self.send(session, 'Peux-tu regarder le document public ?').json()
        self.assertTrue(session['web_confirmation_pending'])
        self.assertEqual(calls, [])
        self.gateway.responses = ['Fait public fiable [S1].']
        before = self.snapshot()
        result = self.send(session, 'Oui, vas-y')
        self.assertEqual(result.status_code, 200, result.text)
        session = result.json()
        self.assertTrue(calls)
        self.assertEqual(session['messages'][-1]['web_sources'][0]['source_id'], 'S1')
        self.assertNotIn('BRUME-823', str(provider.queries))
        self.assertNotIn('BRUME-823', str(self.gateway.calls[-1]))
        count = len(calls)
        session = self.send(session, 'Oui, vas-y').json()
        self.assertEqual(len(calls), count)
        self.assertEqual(before, self.snapshot())
        # Le même lecteur conserve les barrières SSRF et aucun réseau n'atteint localhost.
        result = self.send(session, 'Consulte http://127.0.0.1:8000/health')
        self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(len(calls), count)


class EphemeralStoreTests(unittest.IsolatedAsyncioTestCase):
    """Borne et effacement vérifiés sans temporisation réelle de trente minutes."""

    async def test_limits_expiry_and_cancellation(self):
        from app.ephemeral import EphemeralSessions
        from fastapi import HTTPException
        store = EphemeralSessions()
        session = store.create('general')
        for _ in range(80):
            session.append('texte' * 1000, 'réponse' * 1000)
        self.assertLessEqual(len(session.messages), 100)
        self.assertLessEqual(sum(len(m['content'].encode()) for m in session.messages), 256 * 1024)
        self.assertEqual(len(session.messages) % 2, 0)
        for _ in range(7):
            store.create('general')
        with self.assertRaises(HTTPException):
            store.create('general')
        session.task = asyncio.create_task(asyncio.sleep(60))
        timer = session.expiry
        store.discard(session.id)
        await asyncio.gather(session.task, return_exceptions=True)
        self.assertTrue(session.task.cancelled())
        self.assertTrue(timer.cancelled())
        self.assertEqual(session.messages, [])
        store.clear()
        self.assertEqual(store.sessions, {})

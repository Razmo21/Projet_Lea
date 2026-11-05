"""Arrêt ciblé des réponses : vraie orchestration, inférence et Web contrôlés."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_api import FakeModelController, FakeModelGateway, create_app
from app.preferences import PreferenceChange
from app.web_gateway import WebResearch, WebSource


class CancellableGateway:
    """Attend une annulation asyncio et prouve que le nettoyage est terminé."""

    def __init__(self):
        """Les événements distinguent le début du calcul de sa fermeture effective."""
        self.started = threading.Event()
        self.closed = threading.Event()

    async def generate(self, messages):
        """N'émet jamais une réponse partielle présentée comme complète."""
        self.started.set()
        try:
            await asyncio.sleep(30)
            return "Cette réponse ne doit pas arriver."
        finally:
            await asyncio.sleep(0.02)
            self.closed.set()


class ResponseCancellationTests(unittest.TestCase):
    """Les annulations restent liées au jeton exact, sans modifier une autre activité."""

    def setUp(self):
        """Chaque test possède sa base, son runtime et son modèle contrôlé."""
        self.directory = tempfile.TemporaryDirectory(prefix="lea-stop-", dir=Path(__file__).parent)
        self.app = create_app(Path(self.directory.name) / "test.sqlite3",
                              FakeModelGateway(), model_controller=FakeModelController())
        self.context = TestClient(self.app)
        self.client = self.context.__enter__()
        self.origin = {"Origin": "http://127.0.0.1:5173"}

    def tearDown(self):
        """Aucune opération ni donnée temporaire ne survit au test."""
        self.context.__exit__(None, None, None)
        self.directory.cleanup()

    def interrupted(self, path, body, gateway):
        """Annule pendant l'attente, puis attend la réponse et la libération du moteur."""
        identity = str(uuid4())
        headers = {**self.origin, "X-Lea-Response-ID": identity}
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.client.post, path, json=body, headers=headers)
            self.assertTrue(gateway.started.wait(3))
            self.assertEqual(self.client.post(f"/api/responses/{uuid4()}/cancel").status_code, 404)
            rejected = self.client.post(f"/api/responses/{identity}/cancel",
                                        headers={"Origin": "https://untrusted.example"})
            self.assertEqual(rejected.status_code, 403)
            self.assertFalse(gateway.closed.is_set())
            cancelled = self.client.post(f"/api/responses/{identity}/cancel", headers=self.origin)
            self.assertEqual(cancelled.status_code, 200)
            result = future.result(timeout=5)
        self.assertEqual(result.status_code, 409, result.text)
        self.assertTrue(gateway.closed.is_set())
        self.assertFalse(self.client.get('/api/models/status').json()['generation_active'])
        self.assertEqual(self.app.state.runtime_coordinator.response_operations, {})
        self.assertEqual(self.client.post(f"/api/responses/{identity}/cancel").status_code, 404)
        return result

    def test_general_and_veterinary_stop_and_allow_the_next_turn(self):
        """Les deux profils directs conservent la question interrompue et libèrent le verrou."""
        for profile in ('general', 'veterinary'):
            with self.subTest(profile=profile):
                self.client.post(f'/api/models/{profile}/activate', headers=self.origin)
                gateway = CancellableGateway()
                self.app.state.fixed_model_gateway = gateway
                result = self.interrupted('/api/conversations/messages',
                    {'message': 'Explique ce sujet en détail.', 'expected_profile_id': profile}, gateway)
                history = result.json()['conversation']
                self.assertEqual(len(history['messages']), 1)
                self.assertEqual(history['messages'][0]['error'], 'interrupted')
                self.assertFalse(history['generation_active'])
                self.app.state.fixed_model_gateway = FakeModelGateway()
                following = self.client.post('/api/conversations/messages', json={
                    'message': 'Une autre question.', 'conversation_id': history['id'],
                    'expected_revision': history['revision'],
                })
                self.assertEqual(following.status_code, 200, following.text)

    def test_ephemeral_stop_keeps_previous_turns_and_writes_no_history(self):
        """Le bouton arrête la réponse en RAM sans fermer la session temporaire."""
        session = self.client.post('/api/ephemeral').json()
        path = f"/api/ephemeral/{session['id']}/messages"
        previous = self.client.post(path, json={'message': 'Bonjour', 'expected_revision': 0}).json()
        gateway = CancellableGateway()
        self.app.state.fixed_model_gateway = gateway
        self.interrupted(path, {'message': 'Question interrompue',
                               'expected_revision': previous['revision']}, gateway)
        current = self.app.state.ephemeral.get(session['id']).detail()
        self.assertEqual(current['messages'], previous['messages'])
        self.assertEqual(self.client.get('/api/conversations').json()['conversations'], [])
        self.app.state.fixed_model_gateway = FakeModelGateway()
        self.assertEqual(self.client.post(path, json={
            'message': 'Suite', 'expected_revision': current['revision'],
        }).status_code, 200)

    def test_edit_and_retry_are_also_cancellable(self):
        """Les actions existantes ne créent pas un chemin de génération impossible à arrêter."""
        history = self.client.post('/api/conversations/messages', json={'message': 'Bonjour'}).json()
        identity = str(uuid4())
        gateway = CancellableGateway()
        self.app.state.fixed_model_gateway = gateway
        path = f"/api/conversations/{history['id']}/messages/{history['messages'][0]['id']}"
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.client.patch, path,
                json={'content': 'Texte modifié', 'expected_revision': history['revision']},
                headers={**self.origin, 'X-Lea-Response-ID': identity})
            self.assertTrue(gateway.started.wait(3))
            self.client.post(f'/api/responses/{identity}/cancel', headers=self.origin)
            result = future.result(timeout=5)
        self.assertEqual(result.status_code, 409, result.text)
        self.assertTrue(gateway.closed.is_set())
        history = result.json()['conversation']
        gateway = CancellableGateway()
        self.app.state.fixed_model_gateway = gateway
        self.interrupted(path + '/retry', {'expected_revision': history['revision']}, gateway)

    def test_invalid_and_duplicate_tokens_are_refused(self):
        """Un jeton invalide ou déjà actif ne doit pas enregistrer une seconde question."""
        invalid = self.client.post('/api/conversations/messages', json={'message': 'Bonjour'},
                                   headers={'X-Lea-Response-ID': 'incorrect'})
        self.assertEqual(invalid.status_code, 422)
        gateway = CancellableGateway()
        self.app.state.fixed_model_gateway = gateway
        identity = str(uuid4())
        headers = {'X-Lea-Response-ID': identity}
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.client.post, '/api/conversations/messages',
                                 json={'message': 'Première'}, headers=headers)
            self.assertTrue(gateway.started.wait(3))
            duplicate = self.client.post('/api/conversations/messages',
                                        json={'message': 'Seconde'}, headers=headers)
            self.assertEqual(duplicate.status_code, 409)
            self.client.post(f'/api/responses/{identity}/cancel')
            self.assertEqual(future.result(timeout=5).status_code, 409)
        self.assertEqual(len(self.client.get('/api/conversations').json()['conversations']), 1)

    def test_stop_during_web_collection_releases_resources_and_requires_new_consent(self):
        """L'arrêt commun ferme la collecte et ne permet pas un réessai Web implicite."""
        self.app.state.preferences.save(PreferenceChange(expected_revision=0, web_enabled=True))
        gateway = CancellableGateway()

        async def retrieve(*args, **kwargs):
            """Représente une lecture réseau encore en cours, avec nettoyage observable."""
            return await gateway.generate([])

        with patch.object(self.app.state.web_gateway, 'retrieve', side_effect=retrieve):
            result = self.interrupted('/api/conversations/messages', {
                'message': 'Cherche sur Internet la documentation Python.',
                'web_request_id': str(uuid4()),
            }, gateway)
        history = result.json()['conversation']
        self.assertEqual(history['messages'][0]['failure_kind'], 'web_cancelled')
        self.assertEqual(self.app.state.web_cancellations, {})
        path = f"/api/conversations/{history['id']}/messages/{history['messages'][0]['id']}/retry"
        self.assertEqual(self.client.post(path, json={'expected_revision': history['revision']}).status_code, 409)

    def test_stop_during_web_synthesis_closes_child_generation(self):
        """Les deux niveaux d'annulation Web ne doivent laisser aucun enfant actif."""
        self.app.state.preferences.save(PreferenceChange(expected_revision=0, web_enabled=True))
        gateway = CancellableGateway()
        self.app.state.fixed_model_gateway = gateway
        source = WebSource(title='Documentation', url='https://example.com/docs',
            domain='example.com', snippet='Documentation publique.', provider='fixture',
            consulted_at='2026-11-04T12:00:00Z', retrieval_status='read',
            source_id='S1', evidence_text='Documentation publique.')
        research = WebResearch('[S1] Documentation publique.', (source,))
        with patch.object(self.app.state.web_gateway, 'retrieve', return_value=research):
            result = self.interrupted('/api/conversations/messages', {
                'message': 'Cherche sur Internet la documentation Python.',
                'web_request_id': str(uuid4()),
            }, gateway)
        self.assertEqual(result.json()['conversation']['messages'][0]['failure_kind'], 'web_cancelled')
        self.assertEqual(self.app.state.web_cancellations, {})

import assert from 'node:assert/strict'
import test from 'node:test'
import { isPreferences, requestPreferences } from '../../src/preferences.ts'

test('preferences accept only a valid revision and implemented levels', () => {
  assert.equal(isPreferences({ revision: 0, general_reasoning: 'low', general_reasoning_available: true }), true)
  assert.equal(isPreferences({ revision: 1, general_reasoning: 'high', general_reasoning_available: false }), true)
  for (const value of [null, {}, { revision: -1, general_reasoning: 'high' }, { revision: '0', general_reasoning: 'low' }, { revision: 0, general_reasoning: 'ultra' }]) {
    assert.equal(isPreferences(value), false)
  }
})

test('preferences save the draft through the local controller and require confirmation', async () => {
  // Le transport simulé vérifie qu'aucun chemin de modèle ne part vers le serveur.
  const transport: typeof fetch = async (url, init) => {
    assert.equal(url, '/api/preferences')
    assert.equal(init?.method, 'POST')
    assert.deepEqual(JSON.parse(String(init?.body)), { expected_revision: 2, general_reasoning: 'high' })
    return Response.json({ revision: 3, general_reasoning: 'high', general_reasoning_available: true })
  }
  assert.equal((await requestPreferences({ expected_revision: 2, general_reasoning: 'high' }, transport)).revision, 3)
})

test('preferences refuse malformed confirmations, save errors and unavailable controller', async () => {
  for (const response of [
    Response.json({ revision: 0, general_reasoning: 'low', general_reasoning_available: true }),
    Response.json({ revision: 1, general_reasoning: 'high', general_reasoning_available: true }),
    Response.json({ revision: 3, general_reasoning: 'high', general_reasoning_available: false }),
    Response.json({ detail: 'Conflit' }, { status: 409 }),
    new Response('not json'),
  ]) {
    await assert.rejects(requestPreferences({ expected_revision: 2, general_reasoning: 'high' }, async () => response))
  }
  await assert.rejects(requestPreferences(undefined, async () => { throw new Error('offline') }), /indisponible/)
})

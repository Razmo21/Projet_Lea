import assert from 'node:assert/strict'
import test from 'node:test'
import { defaultVoicePreferences, isPreferences, requestPreferences } from '../../src/preferences.ts'

const profile_settings = [
  { id: 'general', display_name: 'Général', model_name: 'Modèle général', reasoning_available: true },
  { id: 'development', display_name: 'Programmation', model_name: 'Modèle code', reasoning_available: false },
  { id: 'veterinary', display_name: 'Vétérinaire', model_name: 'Modèle vétérinaire', reasoning_available: true },
]
const defaults = {
  ...defaultVoicePreferences,
  veterinary_reasoning: 'high' as const,
  veterinary_reasoning_available: true,
  profile_settings,
}

test('preferences accept only a valid revision and implemented levels', () => {
  assert.equal(defaultVoicePreferences.voice_id, 'lea_voice')
  assert.equal(isPreferences({ ...defaults, revision: 0, general_reasoning: 'low', general_reasoning_available: true, show_resource_chart: false }), true)
  assert.equal(isPreferences({ ...defaults, revision: 1, general_reasoning: 'high', general_reasoning_available: false, show_resource_chart: true }), true)
  for (const value of [null, {}, { revision: -1, general_reasoning: 'high' }, { revision: '0', general_reasoning: 'low' }, { revision: 0, general_reasoning: 'ultra' }]) {
    assert.equal(isPreferences(value), false)
  }
  assert.equal(isPreferences({ ...defaults, voice_id: '', revision: 0, general_reasoning: 'low', general_reasoning_available: true, show_resource_chart: false }), false)
})

test('preferences save the draft through the local controller and require confirmation', async () => {
  // Le transport simulé vérifie qu'aucun chemin de modèle ne part vers le serveur.
  const transport: typeof fetch = async (url, init) => {
    assert.equal(url, '/api/preferences')
    assert.equal(init?.method, 'POST')
    assert.deepEqual(JSON.parse(String(init?.body)), { expected_revision: 2, general_reasoning: 'high' })
    return Response.json({ ...defaults, revision: 3, general_reasoning: 'high', general_reasoning_available: true, show_resource_chart: false })
  }
  assert.equal((await requestPreferences({ expected_revision: 2, general_reasoning: 'high' }, transport)).revision, 3)
})

test('preferences refuse malformed confirmations, save errors and unavailable controller', async () => {
  for (const response of [
    Response.json({ ...defaults, revision: 0, general_reasoning: 'low', general_reasoning_available: true, show_resource_chart: false }),
    Response.json({ ...defaults, revision: 1, general_reasoning: 'high', general_reasoning_available: true, show_resource_chart: false }),
    Response.json({ ...defaults, revision: 3, general_reasoning: 'high', general_reasoning_available: false, show_resource_chart: false }),
    Response.json({ detail: 'Conflit' }, { status: 409 }),
    new Response('not json'),
  ]) {
    await assert.rejects(requestPreferences({ expected_revision: 2, general_reasoning: 'high' }, async () => response))
  }
  await assert.rejects(requestPreferences(undefined, async () => { throw new Error('offline') }), /indisponible/)
})

test('chart preference works without a reasoning capability and requires its own confirmation', async () => {
  const change = { expected_revision: 0, show_resource_chart: true }
  const payload = { ...defaults, revision: 1, general_reasoning: 'low', general_reasoning_available: false, show_resource_chart: true }
  assert.equal((await requestPreferences(change, async () => Response.json(payload))).show_resource_chart, true)
  await assert.rejects(requestPreferences(change, async () => Response.json({ ...payload, show_resource_chart: false })))
  assert.equal(isPreferences({ ...payload, show_resource_chart: 'true' }), false)
})

import assert from 'node:assert/strict'
import test from 'node:test'
import { isResourceSnapshot, resourceNotice, resourcesForProfile } from '../../src/resources.ts'

// Le payload n'a aucune autorité de commande ou d'arrêt d'un processus.
const healthy = { active: true, stale: false, profile_id: 'general', sampled_at: 10, ram: { total_bytes: 100, used_bytes: 60, available_bytes: 40 }, vram: null, cpu_percent: 20, level: 'NORMAL' as const, messages: [] }

test('resource contracts reject impossible readings and retain unknown values', () => {
  assert.equal(isResourceSnapshot(healthy), true)
  assert.equal(isResourceSnapshot({ ...healthy, cpu_percent: null }), true)
  for (const item of [{ ...healthy, ram: {} }, { ...healthy, cpu_percent: 101 }, { ...healthy, cpu_percent: NaN }, { ...healthy, vram: { total_bytes: 10, used_bytes: 11, available_bytes: -1 } }, { ...healthy, level: 'OK' }]) {
    assert.equal(isResourceSnapshot(item), false)
  }
})

test('system readings work for any profile and reject stale profile alerts', () => {
  // Aucun nom de profil ou modèle n'est privilégié dans le diagramme.
  for (const profile_id of ['general', 'development', 'future-local-profile']) {
    const value = { ...healthy, profile_id }
    assert.equal(isResourceSnapshot(value), true)
    assert.equal(resourcesForProfile(value, profile_id), value)
    assert.equal(resourcesForProfile(value, 'another-profile'), null)
    assert.equal(resourcesForProfile({ ...value, active: false }, profile_id), null)
    assert.equal(resourcesForProfile({ ...value, stale: true }, profile_id), null)
  }
  assert.equal(isResourceSnapshot({ ...healthy, profile_id: undefined }), false)
  assert.equal(isResourceSnapshot({ ...healthy, profile_id: '' }), false)
})

test('critical and stale notices do not depend on chart visibility', () => {
  assert.equal(resourceNotice(healthy), '')
  assert.equal(resourceNotice({ ...healthy, level: 'CRITICAL', messages: ['Service requis indisponible.'] }), 'Service requis indisponible.')
  assert.match(resourceNotice({ active: true, stale: true }), /pas confirmé/)
  assert.match(resourceNotice(null), /indisponible/)
})

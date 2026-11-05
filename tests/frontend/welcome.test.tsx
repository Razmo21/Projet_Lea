import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Welcome, {
  nextWelcomeIndex,
  welcomePhrases,
  welcomePhrasesForProfile,
} from '../../src/components/Welcome'

test('Accueil : un nouveau choix reste dans les six phrases et évite la répétition immédiate', () => {
  for (let current = 0; current < welcomePhrases.length; current++) {
    for (let attempt = 0; attempt < 20; attempt++) {
      const next = nextWelcomeIndex(current)
      assert.notEqual(next, current)
      assert.ok(welcomePhrases[next])
    }
  }
})

test('Chaque profil spécialisé possède cinq titres et un choix sans répétition immédiate', () => {
  for (const profileId of ['development', 'veterinary']) {
    const phrases = welcomePhrasesForProfile(profileId)
    assert.equal(new Set(phrases).size, 5)
    for (let current = 0; current < phrases.length; current++) {
      const next = nextWelcomeIndex(current, phrases.length)
      assert.notEqual(current, next)
      const html = renderToStaticMarkup(<Welcome index={next} profileId={profileId} ephemeral={false} />)
      assert.ok(html.includes(phrases[next]))
    }
  }
  assert.equal(welcomePhrasesForProfile('futur-profil'), welcomePhrases)
})

test('Accueil : le titre dépend uniquement du choix fourni et du mode, sans rotation automatique', () => {
  const normal = renderToStaticMarkup(<Welcome index={2} ephemeral={false} />)
  assert.match(normal, /Une question, une idée, un projet/)
  assert.equal(
    normal,
    renderToStaticMarkup(<Welcome index={2} ephemeral={false} />),
  )
  const ephemeral = renderToStaticMarkup(<Welcome index={2} ephemeral />)
  assert.match(ephemeral, /Chat éphémère/)
  assert.doesNotMatch(ephemeral, /Une question/)
})

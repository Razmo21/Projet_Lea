import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import AgentRunResult from '../../src/components/AgentRunResult'
import type { AgentRun } from '../../src/lib/agentRuns'

const completedRun: AgentRun = {
  run_id: 'run-test', conversation_id: null, project_id: 'project-test',
  profile_id: 'development', openhands_session_id: 'session-test',
  task: 'Lis le fichier texte.', state: 'completed',
  started_at: '2026-11-03T03:00:00Z', finished_at: '2026-11-03T03:01:00Z',
  created_at: '2026-11-03T03:00:00Z', updated_at: '2026-11-03T03:01:00Z',
  result_summary: 'Le fichier contient **bonjour**.', failure_detail: null,
  checkpoint_id: null, validation_status: 'validated',
}

// Le composant reçoit le résultat du run ; la présence d'un diff ne le conditionne pas.
function render(changes: Partial<AgentRun> = {}) {
  return renderToStaticMarkup(<AgentRunResult run={{ ...completedRun, ...changes }} />)
}

test('Un run de lecture affiche sa réponse Markdown sans checkpoint ni diff', () => {
  const html = render()
  assert.ok(html.includes('Le fichier contient <strong>bonjour</strong>.'))
  assert.ok(html.includes('Résultat de la tâche'))
  assert.ok(!html.includes('échoué'))
})

test('Une erreur sans réponse affiche le motif backend au lieu de disparaître', () => {
  const html = render({
    state: 'failed', validation_status: 'failed', result_summary: null,
    failure_detail: 'OpenHands a signalé une erreur d’exécution.',
  })
  assert.ok(html.includes('La tâche a échoué'))
  assert.ok(html.includes('Erreur pendant la tâche'))
  assert.ok(!html.includes('bonjour'))
})

test('Une réponse partielle ou historique ne cache pas un échec ou une validation absente', () => {
  const failed = render({ state: 'failed', validation_status: 'failed' })
  assert.ok(failed.includes('La tâche a échoué'))
  assert.ok(failed.includes('<strong>bonjour</strong>'))
  assert.ok(render({ validation_status: undefined }).includes('Changements non validés et non acceptables'))
  assert.ok(render({ state: 'cancelled' }).includes('Tâche annulée'))
  assert.ok(render({ state: 'limit_reached' }).includes('atteint sa limite'))
})

test('Un refus technique est raccourci sans réécrire la réponse ni valider la tâche', () => {
  const summary = 'Lecture effectuée ; résultat **partiel**.'
  const html = render({ state: 'failed', result_summary: summary,
    failure_detail: 'Le projet a changé après le run ; rollback refusé pour éviter un écrasement.',
  })
  assert.ok(html.includes('Restauration refusée car le projet a changé'))
  assert.ok(html.includes('Lecture effectuée ; résultat <strong>partiel</strong>.'))
  assert.ok(html.includes('La tâche a échoué'))
})

test('Aucune réponse n’est inventée pour un résultat vide ou un run encore actif', () => {
  assert.ok(render({ result_summary: '  ' }).includes('Aucune réponse finale'))
  for (const state of ['pending', 'running', 'waiting_for_tool'] as const) {
    const active = render({ state })
    assert.ok(active.includes('Tâche en cours…'))
    assert.ok(!active.includes('bonjour'))
    assert.ok(!active.includes('échoué'))
  }
})

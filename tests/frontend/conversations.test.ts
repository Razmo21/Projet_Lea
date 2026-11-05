import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  allowsDestructiveMessageAction,
  buildSendMessagePayload,
  conversationIdFromSearch,
  createLatestRequestGate,
  isAmbiguousWebRequest,
  isExplicitWebRequest,
  isWebConfirmation,
  isWebFailure,
  messageFailureLabel,
  webAuthorizationForTurn,
  webRetryDraft,
  webSourceKindLabel,
} from '../../src/lib/conversations.ts'
import type { WebSource } from '../../src/lib/conversations.ts'
import type { ConversationDetail } from '../../src/lib/conversations.ts'
import {
  activeModelProfile,
  canActivateModel,
  isModelCatalog,
  isModelRuntimeStatus,
} from '../../src/lib/models.ts'
import { isProjectCatalog } from '../../src/lib/projects.ts'
import {
  agentRunValidationPresentation,
  effectiveValidationStatus,
  isActiveAgentRun,
  isAgentRun,
  isAgentRunChanges,
  latestAgentRunForProject,
  pollingTone,
  recordPollingFailure,
  requireAgentRun,
  resetPollingHealth,
  runtimeStatusPresentation,
} from '../../src/lib/agentRuns.ts'
import type { AgentRun } from '../../src/lib/agentRuns.ts'


const conversation: ConversationDetail = {
  id: '123e4567-e89b-42d3-a456-426614174000',
  title: 'Conversation',
  title_origin: 'automatic',
  created_at: '2026-08-12T00:00:00.000Z',
  updated_at: '2026-08-12T00:00:00.000Z',
  revision: 7,
  generation_active: false,
  message_count: 2,
  messages: [
    {
      id: '223e4567-e89b-42d3-a456-426614174000',
      conversation_id: '123e4567-e89b-42d3-a456-426614174000',
      position: 1,
      role: 'user',
      content: 'Ancienne question',
      status: 'completed',
      kind: 'conversation',
      model_id: null,
      profile_id: null,
      web_sources: [],
      error: null,
      created_at: '2026-08-12T00:00:00.000Z',
      updated_at: '2026-08-12T00:00:00.000Z',
    },
    {
      id: '323e4567-e89b-42d3-a456-426614174000',
      conversation_id: '123e4567-e89b-42d3-a456-426614174000',
      position: 2,
      role: 'assistant',
      content: 'Ancienne réponse',
      status: 'completed',
      kind: 'conversation',
      model_id: 'lea-general',
      profile_id: 'general',
      web_sources: [],
      error: null,
      created_at: '2026-08-12T00:00:00.000Z',
      updated_at: '2026-08-12T00:00:00.000Z',
    },
  ],
}


test('the browser sends only the conversation id, message and expected revision', () => {
  const payload = buildSendMessagePayload(conversation, 'Nouveau message')

  assert.deepEqual(payload, {
    conversation_id: conversation.id,
    message: 'Nouveau message',
    expected_revision: 7,
  })
  assert.equal('web_authorized' in payload, false)
  assert.equal('history' in payload, false)
  assert.equal(JSON.stringify(payload).includes('/no_think'), false)
  assert.equal(JSON.stringify(payload).includes('system'), false)
})


test('a deferred new conversation has no id or revision before its first message', () => {
  assert.deepEqual(buildSendMessagePayload(null, 'Premier message'), {
    conversation_id: null,
    message: 'Premier message',
    expected_revision: null,
  })
})

test('Web consent comes only from explicit wording or the scoped confirmation', () => {
  assert.equal(isExplicitWebRequest('Cherche sur Internet la version actuelle'), true)
  assert.equal(isExplicitWebRequest('https://example.com/article'), true)
  assert.equal(webAuthorizationForTurn('Cherche sur Internet la version actuelle'), true)
  assert.equal(webAuthorizationForTurn('https://example.com/article'), true)
  assert.equal(webAuthorizationForTurn('Une question ordinaire'), false)
  assert.equal(isExplicitWebRequest('Peux-tu regarder cela ?'), false)
  assert.equal(isAmbiguousWebRequest('Peux-tu regarder ce qui se passe ?'), true)
  assert.equal(isWebConfirmation('Oui, vas-y.'), true)
  assert.equal(isWebConfirmation('Oui, cherche'), true)
  assert.equal(isWebConfirmation('Vas-y'), true)
  assert.equal(isWebConfirmation("Toi cherche s'il te plaît"), true)
  assert.equal(isWebConfirmation('Toi, recherche stp.'), true)
  assert.equal(isWebConfirmation('Oui, mais plus tard'), false)
})

test('the question form no longer exposes the obsolete per-turn Web checkbox', () => {
  const appSource = readFileSync(new URL('../../src/App.tsx', import.meta.url), 'utf8')

  assert.equal(appSource.includes('Utiliser le Web uniquement pour cette question'), false)
  assert.equal(appSource.includes('webRequested'), false)
})

test('Web evidence labels distinguish PDFs, transcripts and metadata-only videos', () => {
  const source: WebSource = {
    source_id: 'S1', title: 'Preuve', url: 'https://example.com/preuve',
    domain: 'example.com', snippet: 'Résumé', provider: 'Test',
    consulted_at: '2026-10-24T12:00:00+00:00', published_at: null,
    updated_at: null, document_date: null, retrieval_status: 'read',
    source_kind: 'pdf', limitations: null,
  }
  assert.equal(webSourceKindLabel(source), 'PDF lu')
  assert.equal(webSourceKindLabel({ ...source, source_kind: 'dynamic_html' }), 'page JavaScript lue')
  assert.equal(webSourceKindLabel({ ...source, source_kind: 'video_transcript' }), 'transcription publique')
  assert.equal(webSourceKindLabel({ ...source, source_kind: 'video_metadata' }), 'métadonnées vidéo seulement')
  assert.equal(webSourceKindLabel({ ...source, source_kind: 'search_snippet' }), 'extrait du moteur seulement')
})


test('only a valid UUID is restored from the URL', () => {
  assert.equal(
    conversationIdFromSearch(`?conversation=${conversation.id}`),
    conversation.id,
  )
  assert.equal(conversationIdFromSearch('?conversation=not-an-id'), null)
  assert.equal(conversationIdFromSearch('?search=conversation'), null)
})


test('only the latest conversation request may update the interface', async () => {
  const gate = createLatestRequestGate()
  const applied: string[] = []
  let resolveFirst!: (value: string) => void
  let resolveSecond!: (value: string) => void
  const firstResponse = new Promise<string>((resolve) => { resolveFirst = resolve })
  const secondResponse = new Promise<string>((resolve) => { resolveSecond = resolve })

  async function load(response: Promise<string>) {
    const request = gate.begin()
    const value = await response
    if (gate.isCurrent(request)) applied.push(value)
  }

  const firstLoad = load(firstResponse)
  const secondLoad = load(secondResponse)
  resolveSecond('conversation B')
  await secondLoad
  resolveFirst('conversation A périmée')
  await firstLoad

  assert.deepEqual(applied, ['conversation B'])

  const invalidatedRequest = gate.begin()
  gate.invalidate()
  assert.equal(gate.isCurrent(invalidatedRequest), false)
})


test('a stale error or mutation cannot overwrite a newer navigation', async () => {
  const gate = createLatestRequestGate()
  const staleMutation = gate.current()
  const firstLoad = gate.begin()
  const secondLoad = gate.begin()

  assert.equal(gate.isCurrent(staleMutation), false)
  assert.equal(gate.isCurrent(firstLoad), false)
  assert.equal(gate.isCurrent(secondLoad), true)

  gate.invalidate()
  assert.equal(gate.isCurrent(secondLoad), false)
})


test('only ordinary conversation turns allow destructive message actions', () => {
  assert.equal(
    allowsDestructiveMessageAction({ kind: 'conversation' }),
    true,
  )
  assert.equal(
    allowsDestructiveMessageAction({ kind: 'memory' }),
    false,
  )
})

test('persisted Web failures are not presented as model generation failures', () => {
  assert.equal(
    messageFailureLabel({ error: 'model_error', failure_kind: 'web_blocked' }),
    'Fournisseur Web bloqué.',
  )
  assert.equal(
    messageFailureLabel({ error: 'model_error', failure_kind: 'web_timeout' }),
    'Recherche Web trop lente.',
  )
  assert.equal(
    messageFailureLabel({ error: 'model_error', failure_kind: 'web_extraction' }),
    'Contenu Web inaccessible.',
  )
  assert.equal(
    messageFailureLabel({ error: 'model_error', failure_kind: 'web_extraction' }),
    'Contenu Web inaccessible.',
  )
  assert.equal(
    messageFailureLabel({ error: 'model_error', failure_kind: null }),
    'Échec de la génération.',
  )
  assert.equal(
    messageFailureLabel({ error: 'model_error', failure_kind: 'web_error' }),
    'Recherche ou synthèse Web échouée.',
  )
  assert.equal(isWebFailure({ failure_kind: 'web_blocked' }), true)
  assert.equal(isWebFailure({ failure_kind: 'web_error' }), true)
  assert.equal(isWebFailure({ failure_kind: 'model_error' }), false)
  assert.equal(isWebFailure({ failure_kind: null }), false)
})

test('a failed Web confirmation prepares the original question as a new explicit draft', () => {
  const question = 'Quelle est la température actuelle à Montréal ?'
  const history = [
    { role: 'user' as const, position: 1, content: question },
    { role: 'assistant' as const, position: 2, content: 'Veux-tu que je cherche ?' },
    { role: 'user' as const, position: 3, content: "Toi cherche s'il te plaît" },
  ]

  assert.equal(
    webRetryDraft(history[2], history),
    `Cherche sur Internet : ${question}`,
  )
  assert.equal(
    webRetryDraft(
      { position: 5, content: 'Cherche sur Internet la température actuelle à Montréal' },
      history,
    ),
    'Cherche sur Internet la température actuelle à Montréal',
  )
  assert.equal(
    webRetryDraft({ position: 3, content: 'Oui' }, []),
    '',
  )
})


test('the public model catalog is validated and resolves its active profile', () => {
  const catalog = {
    default_profile_id: 'general',
    active_profile_id: 'general',
    profiles: [
      {
        id: 'general',
        display_name: 'Général',
        model_type: 'chat',
        role: 'general',
        enabled: true,
        display_order: 10,
        context_tokens: 8192,
        max_user_message_bytes: 6000,
        capabilities: ['conversation'],
      },
    ],
  }

  assert.equal(isModelCatalog(catalog), true)
  assert.equal(activeModelProfile(catalog)?.display_name, 'Général')
  assert.equal(activeModelProfile(catalog)?.max_user_message_bytes, 6000)
  assert.equal(isModelCatalog({ ...catalog, profiles: [{ id: 'general' }] }), false)
  assert.equal(
    isModelCatalog({
      ...catalog,
      profiles: [{ ...catalog.profiles[0], max_user_message_bytes: 0 }],
    }),
    false,
  )
  assert.equal(
    isModelCatalog({
      ...catalog,
      profiles: [{ ...catalog.profiles[0], max_user_message_bytes: 6000.5 }],
    }),
    false,
  )
})


test('model activation is blocked while loading, generating or already active', () => {
  const ready = {
    state: 'ready' as const,
    message: 'Prêt.',
    active_profile_id: 'general',
    loading_profile_id: null,
    generation_active: false,
    agent_run_active: false,
  }

  assert.equal(isModelRuntimeStatus(ready), true)
  assert.equal(canActivateModel(ready, 'development'), true)
  assert.equal(canActivateModel(ready, 'general'), false)
  assert.equal(canActivateModel({ ...ready, state: 'loading', loading_profile_id: 'development' }, 'development'), false)
  assert.equal(canActivateModel({ ...ready, generation_active: true }, 'development'), false)
  assert.equal(canActivateModel({ ...ready, agent_run_active: true }, 'development'), false)
  assert.equal(isModelRuntimeStatus({ ...ready, generation_active: 'false' }), false)
})


test('the project catalog accepts only relative public paths and one active id', () => {
  const catalog = {
    active_project_id: '123e4567-e89b-42d3-a456-426614174000',
    projects: [
      {
        id: '123e4567-e89b-42d3-a456-426614174000',
        name: 'Projet Ω',
        relative_path: 'Projet Ω',
        created_at: '2026-08-20T00:00:00.000Z',
        updated_at: '2026-08-20T00:00:00.000Z',
        active: true,
      },
    ],
  }

  assert.equal(isProjectCatalog(catalog), true)
  assert.equal(isProjectCatalog({ ...catalog, projects: [{ ...catalog.projects[0], relative_path: 'C:\\secret' }] }), false)
  assert.equal(isProjectCatalog({ ...catalog, projects: [{ ...catalog.projects[0], relative_path: '\\\\server\\share' }] }), false)
})


test('the browser validates compact persisted OpenHands runs and safe checkpoint diffs', () => {
  const run = {
    run_id: '123e4567-e89b-42d3-a456-426614174000',
    conversation_id: null,
    project_id: '223e4567-e89b-42d3-a456-426614174000',
    profile_id: 'development',
    openhands_session_id: 'sdk-session',
    task: 'Corrige le test',
    state: 'running',
    started_at: '2026-08-28T00:00:00.000Z',
    finished_at: null,
    result_summary: null,
    checkpoint_id: '323e4567-e89b-42d3-a456-426614174000',
    created_at: '2026-08-28T00:00:00.000Z',
    updated_at: '2026-08-28T00:00:00.000Z',
  }
  assert.equal(isAgentRun(run), true)
  assert.equal(isActiveAgentRun(run), true)
  assert.equal(isAgentRun({ ...run, state: 'invented' }), false)
  assert.equal(
    isAgentRunChanges({
      run_id: run.run_id,
      checkpoint: {
        checkpoint_id: run.checkpoint_id,
        run_id: run.run_id,
        project_id: run.project_id,
        project_relative_path: 'Projet',
        project_identity: '1:2',
        state: 'completed',
      },
      changes: [{ relative_path: 'src/main.py', entry_type: 'file', change: 'modified' }],
    }),
    true,
  )
  assert.equal(
    isAgentRunChanges({
      run_id: run.run_id,
      checkpoint: { project_relative_path: 'C:\\secret' },
      changes: [],
    }),
    false,
  )
  assert.equal(
    isAgentRunChanges({
      run_id: run.run_id,
      checkpoint: {
        checkpoint_id: run.checkpoint_id,
        run_id: run.run_id,
        project_id: run.project_id,
        project_relative_path: 'Projet',
        project_identity: '1:2',
        state: 'invented',
      },
      changes: [],
    }),
    false,
  )
})


test('a confirmed ready profile stays non-red after one transient polling failure', () => {
  let health = resetPollingHealth()
  const ready = runtimeStatusPresentation('Programmation', 'ready', 'Prêt.', health)
  assert.equal(`status-${ready.tone}`, 'status-ready')
  assert.equal(ready.message, 'Modèle prêt')

  health = recordPollingFailure(health, 'État du modèle indisponible.')
  assert.equal(pollingTone(health), 'normal')
  assert.equal(runtimeStatusPresentation('Programmation', 'ready', 'Prêt.', health).tone, 'ready')
})


test('all ready profiles share the same label without hiding loading or errors', () => {
  const health = resetPollingHealth()
  for (const profile of ['Général', 'Programmation', 'Vétérinaire', 'Autre profil']) {
    assert.equal(runtimeStatusPresentation(profile, 'ready', 'Prêt.', health).message, 'Modèle prêt')
    assert.equal(runtimeStatusPresentation(profile, 'loading', 'Chargement…', health).message, 'Chargement…')
    assert.equal(runtimeStatusPresentation(profile, 'error', 'Panne.', health).message, 'Panne.')
  }
  assert.notEqual(runtimeStatusPresentation(null, null, null, health).message, 'Modèle prêt')
})

test('persistent polling failures become visible and a valid response resets them', () => {
  let health = resetPollingHealth()
  health = recordPollingFailure(health, 'Premier échec')
  health = recordPollingFailure(health, 'Deuxième échec')
  assert.equal(pollingTone(health), 'warning')
  assert.equal(runtimeStatusPresentation('Programmation', 'ready', 'Prêt.', health).tone, 'warning')

  health = recordPollingFailure(health, 'Troisième échec')
  assert.equal(pollingTone(health), 'error')
  assert.equal(runtimeStatusPresentation('Programmation', 'ready', 'Prêt.', health).tone, 'error')

  health = resetPollingHealth()
  assert.equal(runtimeStatusPresentation('Programmation', 'ready', 'Prêt.', health).tone, 'ready')
  assert.equal(runtimeStatusPresentation('Programmation', 'error', 'Panne du runtime.', health).tone, 'error')
})


test('an invalid run poll payload is an explicit error and runs stay scoped to the active project', () => {
  const activeRun: AgentRun = {
    run_id: '123e4567-e89b-42d3-a456-426614174000',
    conversation_id: null,
    project_id: '223e4567-e89b-42d3-a456-426614174000',
    profile_id: 'development',
    openhands_session_id: 'sdk-session',
    task: 'Corrige le test',
    state: 'completed',
    started_at: '2026-08-28T00:00:00.000Z',
    finished_at: '2026-08-28T00:01:00.000Z',
    result_summary: 'Résultat final vérifié.',
    checkpoint_id: '323e4567-e89b-42d3-a456-426614174000',
    created_at: '2026-08-28T00:00:00.000Z',
    updated_at: '2026-08-28T00:01:00.000Z',
  }
  const previousProjectRun: AgentRun = {
    ...activeRun,
    run_id: '423e4567-e89b-42d3-a456-426614174000',
    project_id: '523e4567-e89b-42d3-a456-426614174000',
  }

  assert.throws(
    () => requireAgentRun({ ...activeRun, result_summary: { raw: 'tool payload' } }),
    /statut du run OpenHands est invalide/,
  )
  assert.equal(
    latestAgentRunForProject([previousProjectRun, activeRun], activeRun.project_id)?.run_id,
    activeRun.run_id,
  )
  assert.equal(latestAgentRunForProject([previousProjectRun], activeRun.project_id), null)
  assert.equal(latestAgentRunForProject([activeRun], null), null)
})


test('only a validated run offers acceptance while historical completed runs stay unverified', () => {
  const historical: AgentRun = {
    run_id: '623e4567-e89b-42d3-a456-426614174000',
    conversation_id: null,
    project_id: '723e4567-e89b-42d3-a456-426614174000',
    profile_id: 'development',
    openhands_session_id: 'sdk-session',
    task: 'Corrige le test',
    state: 'completed',
    started_at: '2026-08-28T00:00:00.000Z',
    finished_at: '2026-08-28T00:01:00.000Z',
    result_summary: 'Run historique.',
    checkpoint_id: '823e4567-e89b-42d3-a456-426614174000',
    created_at: '2026-08-28T00:00:00.000Z',
    updated_at: '2026-08-28T00:01:00.000Z',
  }

  assert.equal(isAgentRun(historical), true)
  assert.equal(effectiveValidationStatus(historical), 'unverified')
  assert.equal(agentRunValidationPresentation(historical).tone, 'warning')
  assert.equal(agentRunValidationPresentation(historical).accepts_changes, false)

  const validated: AgentRun = { ...historical, validation_status: 'validated' }
  assert.equal(isAgentRun(validated), true)
  assert.equal(agentRunValidationPresentation(validated).tone, 'ready')
  assert.equal(agentRunValidationPresentation(validated).accepts_changes, true)

  const failed: AgentRun = {
    ...historical,
    state: 'failed',
    validation_status: 'failed',
  }
  assert.equal(agentRunValidationPresentation(failed).tone, 'error')
  assert.equal(agentRunValidationPresentation(failed).message, 'La validation du run a échoué.')
  assert.equal(agentRunValidationPresentation(failed).accepts_changes, false)
  assert.equal(isAgentRun({ ...validated, validation_status: 'invented' }), false)
})

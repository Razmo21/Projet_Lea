import assert from 'node:assert/strict'
import test from 'node:test'

import {
  allowsDestructiveMessageAction,
  buildSendMessagePayload,
  conversationIdFromSearch,
  createLatestRequestGate,
} from '../../src/conversations.ts'
import type { ConversationDetail } from '../../src/conversations.ts'
import {
  activeModelProfile,
  canActivateModel,
  isModelCatalog,
  isModelRuntimeStatus,
} from '../../src/models.ts'
import { isProjectCatalog } from '../../src/projects.ts'
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
} from '../../src/agentRuns.ts'
import type { AgentRun } from '../../src/agentRuns.ts'


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
  assert.equal(ready.message, 'Programmation est prêt.')

  health = recordPollingFailure(health, 'État du modèle indisponible.')
  assert.equal(pollingTone(health), 'normal')
  assert.equal(runtimeStatusPresentation('Programmation', 'ready', 'Prêt.', health).tone, 'ready')
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

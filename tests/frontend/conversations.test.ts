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
        capabilities: ['conversation'],
      },
    ],
  }

  assert.equal(isModelCatalog(catalog), true)
  assert.equal(activeModelProfile(catalog)?.display_name, 'Général')
  assert.equal(isModelCatalog({ ...catalog, profiles: [{ id: 'general' }] }), false)
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

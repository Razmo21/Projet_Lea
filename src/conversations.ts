export const backendOrigin = 'http://127.0.0.1:8000'
export const maxQuestionBytes = 6000

export type MessageStatus = 'pending' | 'completed' | 'failed'
export type MessageKind = 'conversation' | 'memory'

export type ConversationMessage = {
  id: string
  conversation_id: string
  position: number
  role: 'user' | 'assistant'
  content: string
  status: MessageStatus
  kind: MessageKind
  error: string | null
  created_at: string
  updated_at: string
}

export type ConversationSummary = {
  id: string
  title: string
  title_origin: 'automatic' | 'manual'
  created_at: string
  updated_at: string
  revision: number
  generation_active: boolean
  message_count: number
}

export type ConversationDetail = ConversationSummary & {
  messages: ConversationMessage[]
}

export function allowsDestructiveMessageAction(
  message: Pick<ConversationMessage, 'kind'>,
): boolean {
  return message.kind === 'conversation'
}

// Le navigateur n'envoie jamais l'historique : SQLite et le backend restent autoritaires.
export type SendMessagePayload = {
  conversation_id: string | null
  message: string
  expected_revision: number | null
}

export function createLatestRequestGate() {
  // Un ticket invalide les réponses arrivées après une navigation plus récente.
  let latestRequest = 0

  return {
    begin(): number {
      latestRequest += 1
      return latestRequest
    },
    invalidate(): void {
      latestRequest += 1
    },
    current(): number {
      return latestRequest
    },
    isCurrent(request: number): boolean {
      return request === latestRequest
    },
  }
}

export function buildSendMessagePayload(
  conversation: ConversationDetail | null,
  message: string,
): SendMessagePayload {
  return {
    conversation_id: conversation?.id ?? null,
    message,
    expected_revision: conversation?.revision ?? null,
  }
}

export function conversationIdFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get('conversation')
  return value && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : null
}

export function setConversationInUrl(conversationId: string | null, replace = false): void {
  const url = new URL(window.location.href)
  if (conversationId) {
    url.searchParams.set('conversation', conversationId)
  } else {
    url.searchParams.delete('conversation')
  }
  if (replace) {
    window.history.replaceState({}, '', url)
  } else {
    window.history.pushState({}, '', url)
  }
}

export function formatActivity(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat('fr-CA', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(date)
}

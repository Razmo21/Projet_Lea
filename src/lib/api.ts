import { backendOrigin } from './conversations'
import type { ConversationDetail } from './conversations'

type ApiErrorBody = {
  detail?: string
  conversation?: ConversationDetail
}

export class ApiError extends Error {
  status: number
  conversation?: ConversationDetail

  // Conserve la réponse autoritaire éventuelle pour résoudre les conflits sans nouvelle requête.
  constructor(
    status: number,
    message: string,
    conversation?: ConversationDetail,
  ) {
    super(message)
    this.status = status
    this.conversation = conversation
  }
}

// Centralise les appels backend et conserve les détails structurés des erreurs API.
export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${backendOrigin}${path}`, {
    cache: 'no-store',
    ...init,
    headers: init?.body
      ? { 'Content-Type': 'application/json', ...init.headers }
      : init?.headers,
  })
  let data: unknown = null
  if (response.status !== 204) {
    try {
      data = await response.json()
    } catch {
      data = null
    }
  }
  if (!response.ok) {
    const body = (data ?? {}) as ApiErrorBody
    throw new ApiError(
      response.status,
      typeof body.detail === 'string'
        ? body.detail
        : 'L’opération demandée a échoué.',
      body.conversation,
    )
  }
  return data as T
}

import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  backendOrigin,
  allowsDestructiveMessageAction,
  buildSendMessagePayload,
  conversationIdFromSearch,
  createLatestRequestGate,
  formatActivity,
  maxQuestionBytes,
  setConversationInUrl,
} from './conversations'
import type {
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
} from './conversations'

type CoreState = 'stopped' | 'starting' | 'ready' | 'stopping' | 'error'

type CoreStatus = {
  state: CoreState
  model: string
  backend: string
  message: string
}

type ApiErrorBody = {
  detail?: string
  conversation?: ConversationDetail
}

type GenerationResult = 'completed' | 'persisted-error' | 'failed' | 'blocked'

class ApiError extends Error {
  status: number
  conversation?: ConversationDetail

  constructor(status: number, message: string, conversation?: ConversationDetail) {
    super(message)
    this.status = status
    this.conversation = conversation
  }
}

const initialCoreStatus: CoreStatus = {
  state: 'stopped',
  model: 'stopped',
  backend: 'stopped',
  message: 'Léa est arrêtée.',
}

function isCoreStatus(value: unknown): value is CoreStatus {
  if (typeof value !== 'object' || value === null) {
    return false
  }
  const status = value as Record<string, unknown>
  return (
    typeof status.state === 'string' &&
    typeof status.model === 'string' &&
    typeof status.backend === 'string' &&
    typeof status.message === 'string'
  )
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength
}

async function readCoreStatus(response: Response): Promise<CoreStatus> {
  const data: unknown = await response.json()
  if (!isCoreStatus(data)) {
    throw new Error('Le contrôleur local a renvoyé un état invalide.')
  }
  return data
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
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
      typeof body.detail === 'string' ? body.detail : 'L’opération demandée a échoué.',
      body.conversation,
    )
  }
  return data as T
}

function App() {
  const [question, setQuestion] = useState('')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeConversation, setActiveConversation] = useState<ConversationDetail | null>(null)
  const [search, setSearch] = useState('')
  const [isListLoading, setIsListLoading] = useState(false)
  const [isConversationLoading, setIsConversationLoading] = useState(false)
  const [isGenerating, setIsGenerating] = useState(false)
  const [pendingText, setPendingText] = useState('')
  const [conversationError, setConversationError] = useState('')
  const [copyFeedback, setCopyFeedback] = useState('')
  const [renameDraft, setRenameDraft] = useState<string | null>(null)
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [isRenaming, setIsRenaming] = useState(false)
  const generationLock = useRef(false)
  const renameLock = useRef(false)
  const listRequestNumber = useRef(0)
  const conversationRequests = useRef(createLatestRequestGate())
  const conversationLoadingLock = useRef(false)
  const activeConversationRef = useRef<ConversationDetail | null>(null)
  const [coreStatus, setCoreStatus] = useState<CoreStatus>(initialCoreStatus)
  const [isCoreTransition, setIsCoreTransition] = useState(false)
  const previousCoreState = useRef<CoreState>('stopped')

  const closeEditors = useCallback(() => {
    setRenameDraft(null)
    setEditingMessageId(null)
    setEditDraft('')
  }, [])

  useEffect(() => {
    activeConversationRef.current = activeConversation
  }, [activeConversation])

  const refreshCoreStatus = useCallback(async () => {
    try {
      const controllerResponse = await fetch('/api/core/status', { cache: 'no-store' })
      setCoreStatus(await readCoreStatus(controllerResponse))
    } catch {
      setCoreStatus({
        state: 'error',
        model: 'error',
        backend: 'error',
        message: 'Le contrôleur local de Léa n’est pas disponible.',
      })
    }
  }, [])

  const loadConversations = useCallback(async (searchTerm = '') => {
    const requestNumber = ++listRequestNumber.current
    setIsListLoading(true)
    try {
      const result = await apiRequest<{ conversations: ConversationSummary[] }>(
        `/api/conversations?search=${encodeURIComponent(searchTerm.trim())}`,
      )
      if (requestNumber === listRequestNumber.current) {
        setConversations(result.conversations)
      }
    } catch (error) {
      if (requestNumber === listRequestNumber.current) {
        setConversationError(error instanceof Error ? error.message : 'Liste indisponible.')
      }
    } finally {
      if (requestNumber === listRequestNumber.current) {
        setIsListLoading(false)
      }
    }
  }, [])

  const loadConversation = useCallback(async (conversationId: string, updateUrl = true) => {
    const requestNumber = conversationRequests.current.begin()
    conversationLoadingLock.current = true
    setIsConversationLoading(true)
    try {
      const conversation = await apiRequest<ConversationDetail>(
        `/api/conversations/${conversationId}`,
      )
      if (conversationRequests.current.isCurrent(requestNumber)) {
        setActiveConversation(conversation)
        closeEditors()
        setConversationError('')
        if (updateUrl) {
          setConversationInUrl(conversation.id)
        }
      }
    } catch (error) {
      if (conversationRequests.current.isCurrent(requestNumber)) {
        setConversationError(error instanceof Error ? error.message : 'Conversation indisponible.')
        if (error instanceof ApiError && error.status === 404) {
          setActiveConversation(null)
          closeEditors()
          setConversationInUrl(null, !updateUrl)
        }
      }
    } finally {
      if (conversationRequests.current.isCurrent(requestNumber)) {
        conversationLoadingLock.current = false
        setIsConversationLoading(false)
      }
    }
    return requestNumber
  }, [closeEditors])

  useEffect(() => {
    void refreshCoreStatus()
    const intervalId = window.setInterval(() => {
      if (!isCoreTransition) {
        void refreshCoreStatus()
      }
    }, 5000)
    return () => window.clearInterval(intervalId)
  }, [isCoreTransition, refreshCoreStatus])

  useEffect(() => {
    if (coreStatus.state === 'ready' && previousCoreState.current !== 'ready') {
      void loadConversations(search)
      const requestedConversation =
        conversationIdFromSearch(window.location.search) ?? activeConversationRef.current?.id
      if (requestedConversation) {
        void loadConversation(requestedConversation, false)
      }
    }
    previousCoreState.current = coreStatus.state
  }, [coreStatus.state, loadConversation, loadConversations, search])

  useEffect(() => {
    if (coreStatus.state !== 'ready') {
      return
    }
    const timer = window.setTimeout(() => void loadConversations(search), 250)
    return () => window.clearTimeout(timer)
  }, [coreStatus.state, loadConversations, search])

  useEffect(() => {
    const handlePopState = () => {
      const conversationId = conversationIdFromSearch(window.location.search)
      if (conversationId && coreStatus.state === 'ready') {
        void loadConversation(conversationId, false)
      } else if (conversationId) {
        conversationRequests.current.invalidate()
        conversationLoadingLock.current = false
        setIsConversationLoading(false)
        setActiveConversation(null)
        closeEditors()
        setConversationError('')
      } else if (!conversationId) {
        conversationRequests.current.invalidate()
        conversationLoadingLock.current = false
        setIsConversationLoading(false)
        setActiveConversation(null)
        closeEditors()
        setConversationError('')
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [closeEditors, coreStatus.state, loadConversation])

  async function handleCoreAction(action: 'start' | 'stop') {
    if (isCoreTransition) {
      return
    }
    setIsCoreTransition(true)
    setCoreStatus((current) => ({
      ...current,
      state: action === 'start' ? 'starting' : 'stopping',
      message: action === 'start' ? 'Démarrage de Léa…' : 'Arrêt de Léa…',
    }))
    try {
      const response = await fetch(`/api/core/${action}`, { method: 'POST' })
      const status = await readCoreStatus(response)
      setCoreStatus(status)
      if (!response.ok && response.status !== 409) {
        throw new Error(status.message)
      }
    } catch (error) {
      setCoreStatus({
        state: 'error',
        model: 'error',
        backend: 'error',
        message: error instanceof Error ? error.message : 'L’opération sur Léa a échoué.',
      })
    } finally {
      setIsCoreTransition(false)
    }
  }

  async function refreshAfterMutation(
    conversation: ConversationDetail,
    navigationRequest: number,
  ) {
    if (conversationRequests.current.isCurrent(navigationRequest)) {
      setActiveConversation(conversation)
      setConversationInUrl(conversation.id)
    }
    await loadConversations(search)
  }

  async function handleMutationError(
    error: unknown,
    navigationRequest: number,
    conversationId?: string,
  ) {
    if (!conversationRequests.current.isCurrent(navigationRequest)) {
      return
    }

    let activeRequest = navigationRequest
    if (error instanceof ApiError && error.conversation) {
      setActiveConversation(error.conversation)
      setConversationInUrl(error.conversation.id)
      await loadConversations(search)
    } else if (error instanceof ApiError && error.status === 409 && conversationId) {
      const reloadRequest = await loadConversation(conversationId, false)
      await loadConversations(search)
      if (!conversationRequests.current.isCurrent(reloadRequest)) {
        return
      }
      activeRequest = reloadRequest
    }
    if (conversationRequests.current.isCurrent(activeRequest)) {
      setConversationError(error instanceof Error ? error.message : 'L’opération a échoué.')
    }
  }

  async function runGeneration(
    operation: () => Promise<ConversationDetail>,
    pending = '',
  ): Promise<GenerationResult> {
    if (
      generationLock.current ||
      renameLock.current ||
      conversationLoadingLock.current ||
      isGenerating ||
      coreStatus.state !== 'ready'
    ) {
      return 'blocked'
    }
    generationLock.current = true
    const navigationRequest = conversationRequests.current.current()
    setIsGenerating(true)
    setPendingText(pending)
    setConversationError('')
    try {
      await refreshAfterMutation(await operation(), navigationRequest)
      if (conversationRequests.current.isCurrent(navigationRequest)) {
        setQuestion('')
      }
      return 'completed'
    } catch (error) {
      await handleMutationError(
        error,
        navigationRequest,
        activeConversationRef.current?.id,
      )
      return error instanceof ApiError && error.conversation
        ? 'persisted-error'
        : 'failed'
    } finally {
      generationLock.current = false
      setIsGenerating(false)
      setPendingText('')
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (conversationLoadingLock.current) return
    const submitted = question.trim()
    if (!submitted) {
      setConversationError('Écrivez une question avant de l’envoyer.')
      return
    }
    if (byteLength(submitted) > maxQuestionBytes) {
      setConversationError('La question est trop longue pour le contexte actif de Léa.')
      return
    }
    const payload = buildSendMessagePayload(activeConversation, submitted)
    void runGeneration(
      () =>
        apiRequest<ConversationDetail>('/api/conversations/messages', {
          method: 'POST',
          body: JSON.stringify(payload),
        }),
      submitted,
    )
  }

  function handleNewConversation() {
    if (isGenerating || renameLock.current) return
    conversationRequests.current.invalidate()
    conversationLoadingLock.current = false
    setIsConversationLoading(false)
    setActiveConversation(null)
    closeEditors()
    setQuestion('')
    setPendingText('')
    setConversationError('')
    setConversationInUrl(null)
  }

  function handleRename() {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current
    ) return
    setEditingMessageId(null)
    setEditDraft('')
    setRenameDraft(activeConversation.title)
    setConversationError('')
  }

  async function handleRenameSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      !activeConversation ||
      renameDraft === null ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current
    ) return
    const title = renameDraft.trim()
    if (!title) {
      setConversationError('Le titre ne peut pas être vide.')
      return
    }
    renameLock.current = true
    setIsRenaming(true)
    setConversationError('')
    const navigationRequest = conversationRequests.current.current()
    try {
      const conversation = await apiRequest<ConversationDetail>(
        `/api/conversations/${activeConversation.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            title,
            expected_revision: activeConversation.revision,
          }),
        },
      )
      await refreshAfterMutation(conversation, navigationRequest)
      if (conversationRequests.current.isCurrent(navigationRequest)) {
        setRenameDraft(null)
      }
    } catch (error) {
      await handleMutationError(error, navigationRequest, activeConversation.id)
      if (error instanceof ApiError && error.status === 409) {
        setRenameDraft(null)
      }
    } finally {
      renameLock.current = false
      setIsRenaming(false)
    }
  }

  async function handleDelete() {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current
    ) return
    if (!window.confirm(`Supprimer « ${activeConversation.title} » et tous ses messages ?`)) return
    const navigationRequest = conversationRequests.current.current()
    try {
      await apiRequest<void>(`/api/conversations/${activeConversation.id}`, {
        method: 'DELETE',
        body: JSON.stringify({ expected_revision: activeConversation.revision }),
      })
      if (conversationRequests.current.isCurrent(navigationRequest)) {
        conversationRequests.current.invalidate()
        conversationLoadingLock.current = false
        setIsConversationLoading(false)
        setActiveConversation(null)
        closeEditors()
        setConversationInUrl(null)
        setConversationError('')
      }
      await loadConversations(search)
    } catch (error) {
      await handleMutationError(error, navigationRequest, activeConversation.id)
    }
  }

  function handleEdit(message: ConversationMessage) {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current ||
      message.role !== 'user' ||
      !allowsDestructiveMessageAction(message)
    ) return
    setRenameDraft(null)
    setEditingMessageId(message.id)
    setEditDraft(message.content)
    setConversationError('')
  }

  async function handleEditSubmit(
    event: FormEvent<HTMLFormElement>,
    message: ConversationMessage,
  ) {
    event.preventDefault()
    if (
      !activeConversation ||
      editingMessageId !== message.id ||
      isGenerating ||
      conversationLoadingLock.current ||
      message.role !== 'user' ||
      !allowsDestructiveMessageAction(message)
    ) return
    const content = editDraft.trim()
    if (!content) {
      setConversationError('Le message ne peut pas être vide.')
      return
    }
    if (byteLength(content) > maxQuestionBytes) {
      setConversationError('Le message est trop long pour le contexte actif de Léa.')
      return
    }
    const result = await runGeneration(() =>
      apiRequest<ConversationDetail>(
        `/api/conversations/${activeConversation.id}/messages/${message.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            content,
            expected_revision: activeConversation.revision,
          }),
        },
      ),
    )
    if (result === 'completed' || result === 'persisted-error') {
      setEditingMessageId(null)
      setEditDraft('')
    }
  }

  function handleRegenerate(message: ConversationMessage) {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      message.role !== 'assistant' ||
      !allowsDestructiveMessageAction(message)
    ) return
    void runGeneration(() =>
      apiRequest<ConversationDetail>(
        `/api/conversations/${activeConversation.id}/messages/${message.id}/regenerate`,
        {
          method: 'POST',
          body: JSON.stringify({ expected_revision: activeConversation.revision }),
        },
      ),
    )
  }

  function handleRetry(message: ConversationMessage) {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      message.role !== 'user' ||
      !allowsDestructiveMessageAction(message)
    ) return
    void runGeneration(() =>
      apiRequest<ConversationDetail>(
        `/api/conversations/${activeConversation.id}/messages/${message.id}/retry`,
        {
          method: 'POST',
          body: JSON.stringify({ expected_revision: activeConversation.revision }),
        },
      ),
    )
  }

  async function handleCopy(message: ConversationMessage) {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopyFeedback(`Message ${message.position} copié.`)
    } catch {
      setCopyFeedback('La copie a échoué.')
    }
    window.setTimeout(() => setCopyFeedback(''), 1800)
  }

  return (
    <main>
      <section className="chat" aria-labelledby="page-title">
        <h1 id="page-title">Léa</h1>

        <section className="core-controls" aria-label="Contrôle local de Léa">
          <p className={coreStatus.state === 'error' ? 'core-status core-error' : 'core-status'} aria-live="polite">
            {coreStatus.message}
          </p>
          <div className="core-buttons">
            <button type="button" onClick={() => void handleCoreAction('start')} disabled={isCoreTransition || coreStatus.state === 'ready' || coreStatus.state === 'starting'}>
              Démarrer Léa
            </button>
            <button type="button" className="secondary-button" onClick={() => void handleCoreAction('stop')} disabled={isCoreTransition || coreStatus.state === 'stopped' || coreStatus.state === 'stopping'}>
              Arrêter Léa
            </button>
          </div>
        </section>

        <section className="conversation-browser" aria-label="Conversations locales">
          <label htmlFor="conversation-search">Rechercher une conversation</label>
          <input id="conversation-search" type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Titre ou message" disabled={coreStatus.state !== 'ready'} />
          {isListLoading && <p className="conversation-pending">Chargement des conversations…</p>}
          {!isListLoading && conversations.length === 0 && <p className="conversation-empty">Aucune conversation enregistrée.</p>}
          <div className="conversation-summaries">
            {conversations.map((conversation) => (
              <button key={conversation.id} type="button" className={conversation.id === activeConversation?.id ? 'conversation-summary active' : 'conversation-summary'} onClick={() => void loadConversation(conversation.id)} disabled={isGenerating}>
                <span>{conversation.title}</span>
                <small>{formatActivity(conversation.updated_at)}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="conversation" aria-label="Conversation" aria-busy={isGenerating || isConversationLoading}>
          <div className="conversation-header">
            <h2>{activeConversation?.title ?? 'Nouvelle conversation'}</h2>
            <div className="conversation-actions">
              {activeConversation && (
                <>
                  <button type="button" className="secondary-button compact-button" onClick={handleRename} disabled={isGenerating || isConversationLoading || isRenaming}>Renommer</button>
                  <button type="button" className="danger-button compact-button" onClick={() => void handleDelete()} disabled={isGenerating || isConversationLoading || isRenaming}>Supprimer</button>
                </>
              )}
              <button type="button" className="secondary-button compact-button" onClick={handleNewConversation} disabled={isGenerating || isRenaming}>Nouvelle conversation</button>
            </div>
          </div>

          {activeConversation && renameDraft !== null && (
            <form className="inline-editor rename-editor" onSubmit={(event) => void handleRenameSubmit(event)}>
              <label htmlFor="conversation-title">Nouveau titre</label>
              <input
                id="conversation-title"
                value={renameDraft}
                onChange={(event) => setRenameDraft(event.target.value)}
                maxLength={100}
                autoFocus
                disabled={isRenaming || isGenerating}
              />
              <div className="editor-actions">
                <button type="submit" className="compact-button" disabled={isRenaming || isGenerating || coreStatus.state !== 'ready'}>
                  {isRenaming ? 'Enregistrement…' : 'Enregistrer'}
                </button>
                <button type="button" className="secondary-button compact-button" onClick={() => setRenameDraft(null)} disabled={isRenaming}>Annuler</button>
              </div>
            </form>
          )}

          {!activeConversation && !pendingText && <p className="conversation-empty">La conversation sera enregistrée au premier message.</p>}
          {isConversationLoading && <p className="conversation-pending">Chargement…</p>}
          <div className="conversation-list" aria-live="polite">
            {activeConversation?.messages.map((message) => (
              <article className={`message message-${message.role} message-${message.status}`} key={message.id}>
                <strong>{message.role === 'user' ? 'Vous' : 'Léa'}</strong>
                {editingMessageId === message.id ? (
                  <form className="inline-editor message-editor" onSubmit={(event) => void handleEditSubmit(event, message)}>
                    <label htmlFor={`message-edit-${message.id}`}>Modifier votre message</label>
                    <textarea
                      id={`message-edit-${message.id}`}
                      value={editDraft}
                      onChange={(event) => setEditDraft(event.target.value)}
                      rows={4}
                      autoFocus
                      disabled={isGenerating}
                    />
                    <div className="editor-actions">
                      <button type="submit" className="compact-button" disabled={isGenerating || coreStatus.state !== 'ready'}>
                        {isGenerating ? 'Envoi…' : 'Enregistrer et régénérer'}
                      </button>
                      <button type="button" className="secondary-button compact-button" onClick={() => { setEditingMessageId(null); setEditDraft('') }} disabled={isGenerating}>Annuler</button>
                    </div>
                  </form>
                ) : (
                  <p>{message.content}</p>
                )}
                {message.status === 'failed' && <p className="message-error">Échec de la génération.</p>}
                {editingMessageId !== message.id && (
                  <div className="message-actions">
                    <button type="button" className="text-button" onClick={() => void handleCopy(message)}>Copier</button>
                    {message.role === 'user' && allowsDestructiveMessageAction(message) && <button type="button" className="text-button" onClick={() => handleEdit(message)} disabled={isGenerating || isConversationLoading || isRenaming}>Modifier</button>}
                    {message.role === 'user' && message.status === 'failed' && allowsDestructiveMessageAction(message) && <button type="button" className="text-button" onClick={() => handleRetry(message)} disabled={isGenerating || isConversationLoading || isRenaming || coreStatus.state !== 'ready'}>Réessayer</button>}
                    {message.role === 'assistant' && allowsDestructiveMessageAction(message) && <button type="button" className="text-button" onClick={() => handleRegenerate(message)} disabled={isGenerating || isConversationLoading || isRenaming || coreStatus.state !== 'ready'}>Régénérer</button>}
                  </div>
                )}
              </article>
            ))}
            {pendingText && (
              <article className="message message-user message-pending">
                <strong>Vous</strong>
                <p>{pendingText}</p>
              </article>
            )}
          </div>
          {isGenerating && <p className="conversation-pending">Léa répond…</p>}
          {copyFeedback && <p className="copy-feedback" aria-live="polite">{copyFeedback}</p>}
          {conversationError && <p className="chat-error" role="alert">{conversationError}</p>}
        </section>

        <form onSubmit={handleSubmit}>
          <label htmlFor="question">Votre question</label>
          <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Écrivez votre question" rows={5} disabled={isGenerating || isConversationLoading || isRenaming || coreStatus.state !== 'ready'} />
          <button type="submit" disabled={isGenerating || isConversationLoading || isRenaming || coreStatus.state !== 'ready'}>{isGenerating ? 'Envoi...' : 'Envoyer'}</button>
        </form>
      </section>
    </main>
  )
}

export default App

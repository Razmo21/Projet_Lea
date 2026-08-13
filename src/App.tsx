import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

const backendUrl = 'http://127.0.0.1:8000/chat'
const backendErrorMessage = 'Le modèle local de Léa n’est pas disponible.'
const maxQuestionBytes = 2000
const maxHistoryMessageBytes = 8192
const maxHistoryMessages = 24
const thinkingDelimiters = ['<think>', '</think>', '[Start thinking]', '[End thinking]']

type ChatResponse = {
  answer: string
}

type ConversationMessage = {
  role: 'user' | 'assistant'
  content: string
}

type CoreState = 'stopped' | 'starting' | 'ready' | 'stopping' | 'error'

type CoreStatus = {
  state: CoreState
  model: string
  backend: string
  message: string
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

function isChatResponse(value: unknown): value is ChatResponse {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const response = value as Record<string, unknown>
  const answer = response.answer
  return (
    typeof answer === 'string' &&
    answer.trim().length > 0 &&
    !thinkingDelimiters.some((delimiter) => answer.includes(delimiter))
  )
}

function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength
}

function historyForRequest(messages: ConversationMessage[]): ConversationMessage[] {
  const retained: ConversationMessage[] = []

  // Les messages affichés restent tous en mémoire. Seul le suffixe de paires
  // compatible avec les limites défensives du backend est renvoyé.
  for (let index = messages.length - 2; index >= 0; index -= 2) {
    const userMessage = messages[index]
    const assistantMessage = messages[index + 1]
    if (
      !userMessage ||
      !assistantMessage ||
      userMessage.role !== 'user' ||
      assistantMessage.role !== 'assistant' ||
      byteLength(userMessage.content) > maxHistoryMessageBytes ||
      byteLength(assistantMessage.content) > maxHistoryMessageBytes
    ) {
      break
    }

    retained.unshift({ ...userMessage }, { ...assistantMessage })
    if (retained.length >= maxHistoryMessages) {
      break
    }
  }

  return retained
}

async function readCoreStatus(response: Response): Promise<CoreStatus> {
  const data: unknown = await response.json()
  if (!isCoreStatus(data)) {
    throw new Error('Le contrôleur local a renvoyé un état invalide.')
  }

  return data
}

function App() {
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [pendingQuestion, setPendingQuestion] = useState('')
  const [chatError, setChatError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const isSubmittingRef = useRef(false)
  const [coreStatus, setCoreStatus] = useState<CoreStatus>(initialCoreStatus)
  const [isCoreTransition, setIsCoreTransition] = useState(false)

  const refreshCoreStatus = useCallback(async () => {
    try {
      const controllerResponse = await fetch('/api/core/status', {
        cache: 'no-store',
      })
      const status = await readCoreStatus(controllerResponse)
      setCoreStatus(status)
    } catch {
      setCoreStatus({
        state: 'error',
        model: 'error',
        backend: 'error',
        message: 'Le contrôleur local de Léa n’est pas disponible.',
      })
    }
  }, [])

  useEffect(() => {
    void refreshCoreStatus()
    const intervalId = window.setInterval(() => {
      if (!isCoreTransition) {
        void refreshCoreStatus()
      }
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [isCoreTransition, refreshCoreStatus])

  async function handleCoreAction(action: 'start' | 'stop') {
    if (isCoreTransition) {
      return
    }

    setIsCoreTransition(true)
    setCoreStatus((currentStatus) => ({
      ...currentStatus,
      state: action === 'start' ? 'starting' : 'stopping',
      message: action === 'start' ? 'Démarrage de Léa…' : 'Arrêt de Léa…',
    }))

    try {
      const controllerResponse = await fetch(`/api/core/${action}`, {
        method: 'POST',
      })
      const status = await readCoreStatus(controllerResponse)
      setCoreStatus(status)
      if (!controllerResponse.ok && controllerResponse.status !== 409) {
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (isSubmittingRef.current || isLoading || coreStatus.state !== 'ready') {
      return
    }

    const submittedQuestion = question.trim()
    if (!submittedQuestion) {
      setChatError('Écrivez une question avant de l’envoyer.')
      return
    }
    if (byteLength(submittedQuestion) > maxQuestionBytes) {
      setChatError('La question est trop longue pour le contexte temporaire de Léa.')
      return
    }

    const history = historyForRequest(messages)
    isSubmittingRef.current = true
    setIsLoading(true)
    setChatError('')
    setPendingQuestion(submittedQuestion)
    setQuestion('')

    try {
      const backendResponse = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ question: submittedQuestion, history }),
      })

      if (!backendResponse.ok) {
        throw new Error('Backend request failed')
      }

      const data: unknown = await backendResponse.json()
      if (!isChatResponse(data)) {
        throw new Error('Backend response is invalid')
      }

      setMessages((currentMessages) => [
        ...currentMessages,
        { role: 'user', content: submittedQuestion },
        { role: 'assistant', content: data.answer.trim() },
      ])
      setPendingQuestion('')
    } catch {
      setQuestion(submittedQuestion)
      setPendingQuestion('')
      setChatError(backendErrorMessage)
    } finally {
      isSubmittingRef.current = false
      setIsLoading(false)
    }
  }

  function handleNewConversation() {
    if (isSubmittingRef.current || isLoading) {
      return
    }

    setMessages([])
    setQuestion('')
    setPendingQuestion('')
    setChatError('')
  }

  return (
    <main>
      <section className="chat" aria-labelledby="page-title">
        <h1 id="page-title">Léa</h1>

        <section className="core-controls" aria-label="Contrôle local de Léa">
          <p
            className={coreStatus.state === 'error' ? 'core-status core-error' : 'core-status'}
            aria-live="polite"
          >
            {coreStatus.message}
          </p>
          <div className="core-buttons">
            <button
              type="button"
              onClick={() => void handleCoreAction('start')}
              disabled={
                isCoreTransition ||
                coreStatus.state === 'ready' ||
                coreStatus.state === 'starting'
              }
            >
              Démarrer Léa
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void handleCoreAction('stop')}
              disabled={
                isCoreTransition ||
                coreStatus.state === 'stopped' ||
                coreStatus.state === 'stopping'
              }
            >
              Arrêter Léa
            </button>
          </div>
        </section>

        <section className="conversation" aria-label="Conversation" aria-busy={isLoading}>
          <div className="conversation-header">
            <h2>Conversation</h2>
            <button
              type="button"
              className="secondary-button new-conversation-button"
              onClick={handleNewConversation}
              disabled={isLoading}
            >
              Nouvelle conversation
            </button>
          </div>

          {messages.length === 0 && !pendingQuestion && (
            <p className="conversation-empty">La conversation est temporaire et reste dans cette page.</p>
          )}

          <div className="conversation-list" aria-live="polite">
            {messages.map((message, index) => (
              <article className={`message message-${message.role}`} key={`${message.role}-${index}`}>
                <strong>{message.role === 'user' ? 'Vous' : 'Léa'}</strong>
                <p>{message.content}</p>
              </article>
            ))}
            {pendingQuestion && (
              <article className="message message-user message-pending">
                <strong>Vous</strong>
                <p>{pendingQuestion}</p>
              </article>
            )}
          </div>

          {isLoading && <p className="conversation-pending">Léa réfléchit…</p>}
          {chatError && (
            <p className="chat-error" role="alert">
              {chatError}
            </p>
          )}
        </section>

        <form onSubmit={handleSubmit}>
          <label htmlFor="question">Votre question</label>
          <textarea
            id="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Écrivez votre question"
            rows={5}
            disabled={isLoading || coreStatus.state !== 'ready'}
          />
          <button type="submit" disabled={isLoading || coreStatus.state !== 'ready'}>
            {isLoading ? 'Envoi...' : 'Envoyer'}
          </button>
        </form>
      </section>
    </main>
  )
}

export default App

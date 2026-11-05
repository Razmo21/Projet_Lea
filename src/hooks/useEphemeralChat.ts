import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiRequest } from '../lib/api'
import { backendOrigin } from '../lib/conversations'
import type { ConversationDetail } from '../lib/conversations'

type Session = ConversationDetail & { instance_id: string }

// Ce contexte ne quitte jamais la RAM du navigateur et n'utilise pas les routes persistantes.
export function useEphemeralChat(
  instanceId: string | undefined,
  stopped: boolean,
) {
  const [conversation, setConversation] = useState<Session | null>(null)
  const [busy, setBusy] = useState(false)
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')
  const session = useRef<Session | null>(null)
  const operation = useRef<AbortController | null>(null)
  const responseId = useRef<string | null>(null)
  const stopRequested = useRef(false)

  // Arrête le tour en cours sans effacer les échanges précédents ni quitter ce mode.
  async function cancel() {
    if (!responseId.current || stopRequested.current) return
    stopRequested.current = true
    try {
      await apiRequest(`/api/responses/${responseId.current}/cancel`, { method: 'POST' })
    } catch (failure) {
      stopRequested.current = false
      setError(failure instanceof Error ? failure.message : 'Arrêt non confirmé.')
      throw failure
    }
  }

  // Invalide aussi une réponse en vol, pour qu'elle ne réaffiche pas un texte effacé.
  const forget = useCallback(() => {
    operation.current?.abort()
    operation.current = null
    session.current = null
    setConversation(null)
    setPending('')
    setError('')
    setBusy(false)
    setSending(false)
  }, [])

  // Le statut déjà surveillé identifie un backend redémarré, sans nouvelle boucle réseau.
  useEffect(() => {
    if (
      stopped ||
      (instanceId &&
        session.current &&
        session.current.instance_id !== instanceId)
    )
      forget()
  }, [instanceId, stopped, forget])

  useEffect(() => {
    // Ferme au rechargement et à la sortie du document, même s'il rejoint le cache de navigation.
    const leave = () => {
      const id = session.current?.id
      forget()
      if (id)
        void fetch(`${backendOrigin}/api/ephemeral/${id}`, {
          method: 'DELETE',
          keepalive: true,
        }).catch(() => {
          /* Une fermeture brutale reste couverte par l'expiration serveur. */
        })
    }
    window.addEventListener('pagehide', leave)
    return () => {
      window.removeEventListener('pagehide', leave)
      leave()
    }
  }, [forget])

  // Attend la confirmation de fermeture avant de quitter le mode quand le backend est disponible.
  async function toggle(): Promise<boolean> {
    if (operation.current && !session.current) return false
    // Le même bouton peut fermer une réponse ou une recherche Web en cours.
    operation.current?.abort()
    const controller = new AbortController()
    operation.current = controller
    setBusy(true)
    setError('')
    try {
      if (session.current) {
        await apiRequest(`/api/ephemeral/${session.current.id}`, {
          method: 'DELETE',
          signal: controller.signal,
        })
        forget()
      } else {
        const created = await apiRequest<Session>('/api/ephemeral', {
          method: 'POST',
          signal: controller.signal,
        })
        if (controller.signal.aborted) return false
        session.current = created
        setConversation(created)
      }
      return true
    } catch (failure) {
      if (!controller.signal.aborted)
        setError(
          failure instanceof Error
            ? failure.message
            : 'Chat éphémère indisponible.',
        )
      return false
    } finally {
      if (operation.current === controller) {
        operation.current = null
        setBusy(false)
      }
    }
  }

  // Texte et voix empruntent le même endpoint RAM, avec contrôle de révision et annulation.
  async function send(text: string, signal?: AbortSignal): Promise<string> {
    const current = session.current
    if (!current || operation.current || signal?.aborted)
      throw new Error('Chat éphémère indisponible.')
    const controller = new AbortController()
    const abort = () => {
      controller.abort()
      forget()
      void fetch(`${backendOrigin}/api/ephemeral/${current.id}`, {
        method: 'DELETE',
        keepalive: true,
      }).catch(() => {
        /* L'expiration serveur couvre un backend devenu injoignable. */
      })
    }
    signal?.addEventListener('abort', abort, { once: true })
    operation.current = controller
    const identity = crypto.randomUUID()
    responseId.current = identity
    stopRequested.current = false
    setSending(true)
    setPending(text)
    setError('')
    try {
      const detail = await apiRequest<ConversationDetail>(
        `/api/ephemeral/${current.id}/messages`,
        {
          method: 'POST',
          signal: controller.signal,
          headers: { 'X-Lea-Response-ID': identity },
          body: JSON.stringify({
            message: text,
            expected_revision: current.revision,
          }),
        },
      )
      if (controller.signal.aborted || session.current?.id !== current.id)
        throw new Error('Chat éphémère fermé.')
      const updated = { ...detail, instance_id: current.instance_id }
      session.current = updated
      setConversation(updated)
      return detail.messages.at(-1)?.content ?? ''
    } catch (failure) {
      if (stopRequested.current && failure instanceof ApiError && failure.status === 409) {
        setError('La réponse a été interrompue.')
        return ''
      }
      if (!controller.signal.aborted) {
        if (failure instanceof ApiError && failure.status === 410) forget()
        setError(
          failure instanceof Error
            ? failure.message
            : 'La réponse éphémère a échoué.',
        )
      }
      throw failure
    } finally {
      signal?.removeEventListener('abort', abort)
      if (responseId.current === identity) responseId.current = null
      if (operation.current === controller) {
        operation.current = null
        setSending(false)
        setPending('')
      }
    }
  }

  return {
    active: conversation !== null,
    conversation,
    busy,
    sending,
    pending,
    error,
    toggle,
    send,
    cancel,
    forget,
  }
}

import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  backendOrigin,
  allowsDestructiveMessageAction,
  buildSendMessagePayload,
  conversationIdFromSearch,
  createLatestRequestGate,
  formatActivity,
  setConversationInUrl,
} from './conversations'
import type {
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
} from './conversations'
import {
  activeModelProfile,
  canActivateModel,
  isModelCatalog,
  isModelRuntimeStatus,
} from './models'
import type { ModelCatalog, ModelRuntimeStatus } from './models'
import { isProjectCatalog } from './projects'
import type { ProjectCatalog } from './projects'
import {
  agentRunValidationPresentation,
  isActiveAgentRun,
  isAgentRun,
  isAgentRunChanges,
  isAgentRunList,
  latestAgentRunForProject,
  pollingTone,
  recordPollingFailure,
  requireAgentRun,
  resetPollingHealth,
  runtimeStatusPresentation,
} from './agentRuns'
import type { AgentRun, AgentRunChanges, PollingHealth } from './agentRuns'

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

  // Conserve la réponse autoritaire éventuelle pour résoudre les conflits sans nouvelle requête.
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

// Valide la réponse du contrôleur local avant de l'utiliser dans l'interface.
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

// Mesure les octets réellement envoyés plutôt que le nombre de caractères JavaScript.
function byteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength
}

// Parse un statut du cœur et transforme toute réponse partielle en erreur explicite.
async function readCoreStatus(response: Response): Promise<CoreStatus> {
  const data: unknown = await response.json()
  if (!isCoreStatus(data)) {
    throw new Error('Le contrôleur local a renvoyé un état invalide.')
  }
  return data
}

// Centralise les appels backend et conserve les détails structurés des erreurs API.
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

// Orchestre l'interface locale sans dupliquer l'état autoritaire du backend.
function App() {
  // État visible : brouillon, liste locale, conversation active et éditeurs.
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

  // Verrous synchrones : ils bloquent les doubles clics avant le prochain rendu React.
  const generationLock = useRef(false)
  const renameLock = useRef(false)
  const listRequestNumber = useRef(0)
  const conversationRequests = useRef(createLatestRequestGate())
  const conversationLoadingLock = useRef(false)
  const questionInput = useRef<HTMLTextAreaElement>(null)
  const activeConversationRef = useRef<ConversationDetail | null>(null)
  const [coreStatus, setCoreStatus] = useState<CoreStatus>(initialCoreStatus)
  const [corePollingHealth, setCorePollingHealth] = useState<PollingHealth>(resetPollingHealth)
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelRuntimeStatus | null>(null)
  const [modelError, setModelError] = useState('')
  const [modelPollingHealth, setModelPollingHealth] = useState<PollingHealth>(resetPollingHealth)
  const [requestedProfileId, setRequestedProfileId] = useState<string | null>(null)
  const [isModelTransition, setIsModelTransition] = useState(false)
  const [projectCatalog, setProjectCatalog] = useState<ProjectCatalog | null>(null)
  const [projectError, setProjectError] = useState('')
  const [isProjectTransition, setIsProjectTransition] = useState(false)
  const [agentTask, setAgentTask] = useState('')
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null)
  const [agentChanges, setAgentChanges] = useState<AgentRunChanges | null>(null)
  const [agentError, setAgentError] = useState('')
  const [agentPollingError, setAgentPollingError] = useState('')
  const [agentPollingHealth, setAgentPollingHealth] = useState<PollingHealth>(resetPollingHealth)
  const [isAgentStarting, setIsAgentStarting] = useState(false)
  const [isAgentCancelling, setIsAgentCancelling] = useState(false)
  const [isCheckpointTransition, setIsCheckpointTransition] = useState(false)
  const [isCoreTransition, setIsCoreTransition] = useState(false)
  const modelTransitionLock = useRef(false)
  const projectTransitionLock = useRef(false)
  const previousCoreState = useRef<CoreState>('stopped')
  const corePollingHealthRef = useRef<PollingHealth>(resetPollingHealth())
  const modelPollingHealthRef = useRef<PollingHealth>(resetPollingHealth())
  const agentPollingHealthRef = useRef<PollingHealth>(resetPollingHealth())

  // Ferme ensemble les deux éditeurs afin d'éviter des brouillons attachés à une autre conversation.
  const closeEditors = useCallback(() => {
    setRenameDraft(null)
    setEditingMessageId(null)
    setEditDraft('')
  }, [])

  // Rend le focus à la question après une mutation ou un changement de conversation.
  const focusQuestion = useCallback(() => {
    // Le bouton supprimé perd le focus avec son panneau. Attendre le rendu
    // permet de rendre immédiatement le clavier à la zone de saisie.
    window.requestAnimationFrame(() => questionInput.current?.focus())
  }, [])

  // Garde une référence synchrone vers la conversation visible pour les callbacks asynchrones.
  useEffect(() => {
    activeConversationRef.current = activeConversation
  }, [activeConversation])

  // Contrôle du cœur local (modèle + backend), servi par le middleware Vite limité.
  const refreshCoreStatus = useCallback(async () => {
    if (modelTransitionLock.current) {
      return
    }
    try {
      const controllerResponse = await fetch('/api/core/status', { cache: 'no-store' })
      const status = await readCoreStatus(controllerResponse)
      if (!modelTransitionLock.current) {
        const health = resetPollingHealth()
        corePollingHealthRef.current = health
        setCorePollingHealth(health)
        setCoreStatus(status)
      }
    } catch {
      if (!modelTransitionLock.current) {
        const health = recordPollingFailure(
          corePollingHealthRef.current,
          'Le contrôleur local de Léa n’est pas disponible.',
        )
        corePollingHealthRef.current = health
        setCorePollingHealth(health)
        if (pollingTone(health) === 'error') {
          setCoreStatus({
            state: 'error',
            model: 'error',
            backend: 'error',
            message: 'Le contrôleur local de Léa n’est pas disponible.',
          })
        }
      }
    }
  }, [])

  // Le registre public vient du backend ; aucun profil n'est recopié dans React.
  const loadModelCatalog = useCallback(async () => {
    try {
      const catalog = await apiRequest<unknown>('/api/models')
      if (!isModelCatalog(catalog)) {
        throw new Error('Le catalogue des profils est invalide.')
      }
      setModelCatalog(catalog)
      setModelError('')
    } catch (error) {
      setModelCatalog(null)
      setModelError(error instanceof Error ? error.message : 'Catalogue des profils indisponible.')
    }
  }, [])

  // Le statut runtime est distinct du catalogue afin d'exposer les bascules longues.
  const refreshModelStatus = useCallback(async () => {
    try {
      const status = await apiRequest<unknown>('/api/models/status')
      if (!isModelRuntimeStatus(status)) {
        throw new Error('Le runtime a renvoyé un état de modèle invalide.')
      }
      const health = resetPollingHealth()
      modelPollingHealthRef.current = health
      setModelPollingHealth(health)
      setModelStatus(status)
      // A confirmed response supersedes any earlier transient polling or
      // activation error; actual runtime errors remain visible via `status`.
      setModelError('')
      return status
    } catch (error) {
      const message = error instanceof Error ? error.message : 'État du modèle indisponible.'
      const health = recordPollingFailure(modelPollingHealthRef.current, message)
      modelPollingHealthRef.current = health
      setModelPollingHealth(health)
      return null
    }
  }, [])

  // Les projets viennent du registre SQLite ; aucun chemin absolu n'atteint React.
  const loadProjects = useCallback(async () => {
    try {
      const catalog = await apiRequest<unknown>('/api/projects')
      if (!isProjectCatalog(catalog)) {
        throw new Error('Le registre des projets est invalide.')
      }
      setProjectCatalog(catalog)
      setProjectError('')
      return catalog
    } catch (error) {
      setProjectCatalog(null)
      setProjectError(error instanceof Error ? error.message : 'Registre des projets indisponible.')
      return null
    }
  }, [])

  // Lit le diff calculé par le backend ; React ne reconstitue jamais de snapshot local.
  const loadAgentChanges = useCallback(async (runId: string) => {
    try {
      const payload = await apiRequest<unknown>(`/api/agent-runs/${encodeURIComponent(runId)}/changes`)
      if (!isAgentRunChanges(payload)) {
        throw new Error('Le checkpoint du run est invalide.')
      }
      setAgentChanges(payload)
      setAgentError('')
      return payload
    } catch (error) {
      setAgentChanges(null)
      setAgentError(error instanceof Error ? error.message : 'Les changements du run sont indisponibles.')
      return null
    }
  }, [])

  // Récupère seulement le dernier run du projet actif, sans transcript OpenHands ni historique d'un autre projet.
  const loadLatestAgentRun = useCallback(async (projectId: string | null) => {
    if (!projectId) {
      const health = resetPollingHealth()
      agentPollingHealthRef.current = health
      setAgentPollingHealth(health)
      setAgentPollingError('')
      setAgentRun(null)
      setAgentChanges(null)
      return null
    }
    try {
      const payload = await apiRequest<unknown>('/api/agent-runs')
      if (!isAgentRunList(payload)) {
        throw new Error('La liste des runs OpenHands est invalide.')
      }
      const health = resetPollingHealth()
      agentPollingHealthRef.current = health
      setAgentPollingHealth(health)
      setAgentPollingError('')
      setAgentError('')
      const latest = latestAgentRunForProject(payload.runs, projectId)
      setAgentRun(latest)
      if (latest?.checkpoint_id && !isActiveAgentRun(latest)) {
        await loadAgentChanges(latest.run_id)
      } else if (!latest) {
        setAgentChanges(null)
      }
      return latest
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : 'Les runs OpenHands sont indisponibles.')
      return null
    }
  }, [loadAgentChanges])

  // Chargement et navigation : seule la requête la plus récente peut modifier l'écran.
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

  // Charge une conversation seulement si aucune navigation plus récente n'a pris sa place.
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

  // Synchronise l'interface avec les redémarrages du cœur et l'URL du navigateur.
  // Recharge les données autoritaires quand le cœur vient de devenir disponible.
  useEffect(() => {
    void refreshCoreStatus()
    const intervalId = window.setInterval(() => {
      if (!isCoreTransition) {
        void refreshCoreStatus()
      }
    }, 5000)
    return () => window.clearInterval(intervalId)
  }, [isCoreTransition, refreshCoreStatus])

  // Sonde le profil actif tant que le backend est prêt et oublie l'ancien état sinon.
  useEffect(() => {
    if (coreStatus.state === 'ready' && previousCoreState.current !== 'ready') {
      void loadModelCatalog()
      void refreshModelStatus()
      void loadConversations(search)
      const requestedConversation =
        conversationIdFromSearch(window.location.search) ?? activeConversationRef.current?.id
      if (requestedConversation) {
        void loadConversation(requestedConversation, false)
      }
    }
    previousCoreState.current = coreStatus.state
  }, [coreStatus.state, loadConversation, loadConversations, loadModelCatalog, refreshModelStatus, search])

  // Charge les projets seulement pour un profil qui annonce cette capacité.
  useEffect(() => {
    if (coreStatus.state !== 'ready') {
      const health = resetPollingHealth()
      modelPollingHealthRef.current = health
      setModelPollingHealth(health)
      setModelStatus(null)
      setRequestedProfileId(null)
      return
    }
    const intervalId = window.setInterval(() => void refreshModelStatus(), 2000)
    return () => window.clearInterval(intervalId)
  }, [coreStatus.state, refreshModelStatus])

  // Suit un run actif jusqu'à son état final puis récupère son diff persistant.
  useEffect(() => {
    const profile = modelCatalog ? activeModelProfile(modelCatalog) : null
    if (coreStatus.state === 'ready' && profile?.capabilities.includes('workspace_projects')) {
      void loadProjects()
    } else {
      const health = resetPollingHealth()
      agentPollingHealthRef.current = health
      setAgentPollingHealth(health)
      setAgentPollingError('')
      setProjectCatalog(null)
      setProjectError('')
      setAgentRun(null)
      setAgentChanges(null)
      setAgentError('')
    }
  }, [coreStatus.state, loadProjects, modelCatalog])

  // Recharge le dernier run uniquement quand le projet actif est connu, afin de ne jamais réafficher un autre projet.
  useEffect(() => {
    const profile = modelCatalog ? activeModelProfile(modelCatalog) : null
    if (coreStatus.state === 'ready' && profile?.capabilities.includes('workspace_projects')) {
      void loadLatestAgentRun(projectCatalog?.active_project_id ?? null)
    }
  }, [coreStatus.state, loadLatestAgentRun, modelCatalog, projectCatalog?.active_project_id])

  // Suit le run courant jusqu'à sa fin et arrête le polling au démontage de l'effet.
  useEffect(() => {
    const activeRunId = agentRun?.run_id
    if (!activeRunId || !isActiveAgentRun(agentRun)) return
    let cancelled = false
    // Ignore toute réponse arrivée après le démontage de cet effet de polling.
    const refreshRun = async () => {
      try {
        const payload = await apiRequest<unknown>(`/api/agent-runs/${encodeURIComponent(activeRunId)}`)
        if (cancelled) return
        if (!isAgentRun(payload)) {
          setAgentPollingError('Le statut du run OpenHands est invalide.')
          return
        }
        const run = requireAgentRun(payload)
        const health = resetPollingHealth()
        agentPollingHealthRef.current = health
        setAgentPollingHealth(health)
        setAgentPollingError('')
        setAgentRun(run)
        if (!isActiveAgentRun(run) && run.checkpoint_id) {
          await loadAgentChanges(run.run_id)
        }
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Le statut du run OpenHands est indisponible.'
          const health = recordPollingFailure(agentPollingHealthRef.current, message)
          agentPollingHealthRef.current = health
          setAgentPollingHealth(health)
        }
      }
    }
    void refreshRun()
    const intervalId = window.setInterval(() => void refreshRun(), 1500)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [agentRun, loadAgentChanges])

  // Diffère légèrement la recherche pour ne pas interroger SQLite à chaque frappe.
  useEffect(() => {
    if (coreStatus.state !== 'ready') {
      return
    }
    const timer = window.setTimeout(() => void loadConversations(search), 250)
    return () => window.clearTimeout(timer)
  }, [coreStatus.state, loadConversations, search])

  // Aligne la conversation visible sur les boutons précédent et suivant du navigateur.
  useEffect(() => {
    // Restaure l'UUID de l'URL ou revient proprement à une nouvelle conversation.
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

  // Demande au contrôleur Vite une transition du cœur et bloque les doubles clics.
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
      const health = resetPollingHealth()
      corePollingHealthRef.current = health
      setCorePollingHealth(health)
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

  // Active un autre profil seulement après les contrôles d'activité côté client et serveur.
  async function handleModelChange(profileId: string) {
    if (
      modelTransitionLock.current ||
      isModelTransition ||
      isGenerating ||
      coreStatus.state !== 'ready' ||
      !canActivateModel(modelStatus, profileId)
    ) return

    modelTransitionLock.current = true
    setIsModelTransition(true)
    setRequestedProfileId(profileId)
    setModelError('')
    const health = resetPollingHealth()
    modelPollingHealthRef.current = health
    setModelPollingHealth(health)
    setModelStatus((current) => current && ({
      ...current,
      state: 'loading',
      loading_profile_id: profileId,
      message: 'Chargement du profil sélectionné…',
    }))
    try {
      const activated = await apiRequest<unknown>(`/api/models/${encodeURIComponent(profileId)}/activate`, {
        method: 'POST',
      })
      if (!isModelRuntimeStatus(activated)) {
        throw new Error('Le backend n’a pas confirmé le nouveau profil.')
      }
      setModelStatus(activated)
      setModelError('')
      await loadModelCatalog()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Le changement de profil a échoué.'
      await Promise.all([loadModelCatalog(), refreshModelStatus()])
      setModelError(message)
    } finally {
      modelTransitionLock.current = false
      setIsModelTransition(false)
      setRequestedProfileId(null)
    }
  }

  // Redécouvre les projets autorisés puis recharge la sélection persistée.
  async function refreshProjects() {
    if (projectTransitionLock.current || isProjectTransition || isGenerating) return
    projectTransitionLock.current = true
    setIsProjectTransition(true)
    setProjectError('')
    try {
      const catalog = await apiRequest<unknown>('/api/projects/refresh', { method: 'POST' })
      if (!isProjectCatalog(catalog)) {
        throw new Error('Le backend n’a pas confirmé l’actualisation des projets.')
      }
      setProjectCatalog(catalog)
    } catch (error) {
      setProjectError(error instanceof Error ? error.message : 'Actualisation des projets échouée.')
    } finally {
      projectTransitionLock.current = false
      setIsProjectTransition(false)
    }
  }

  // Active un projet par UUID public sans jamais envoyer de chemin depuis le navigateur.
  async function selectProject(projectId: string) {
    if (!projectId || projectTransitionLock.current || isProjectTransition || isGenerating) return
    projectTransitionLock.current = true
    setIsProjectTransition(true)
    setProjectError('')
    try {
      const catalog = await apiRequest<unknown>(`/api/projects/${encodeURIComponent(projectId)}/activate`, {
        method: 'POST',
      })
      if (!isProjectCatalog(catalog)) {
        throw new Error('Le backend n’a pas confirmé le projet actif.')
      }
      setProjectCatalog(catalog)
    } catch (error) {
      setProjectError(error instanceof Error ? error.message : 'Sélection du projet échouée.')
      await loadProjects()
    } finally {
      projectTransitionLock.current = false
      setIsProjectTransition(false)
    }
  }

  // Démarre un seul run backend sur le projet actif ; le chemin ne vient jamais du navigateur.
  async function startAgentRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const task = agentTask.trim()
    if (
      !task ||
      isAgentStarting ||
      isActiveAgentRun(agentRun) ||
      coreStatus.state !== 'ready' ||
      modelStatus?.active_profile_id !== 'development' ||
      !projectCatalog?.active_project_id
    ) return
    setIsAgentStarting(true)
    setAgentError('')
    const health = resetPollingHealth()
    agentPollingHealthRef.current = health
    setAgentPollingHealth(health)
    setAgentPollingError('')
    setAgentChanges(null)
    try {
      const payload = await apiRequest<unknown>('/api/agent-runs', {
        method: 'POST',
        body: JSON.stringify({ task }),
      })
      if (!isAgentRun(payload)) {
        throw new Error('Le backend n’a pas confirmé le run OpenHands.')
      }
      setAgentRun(payload)
      setAgentTask('')
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : 'Le run OpenHands n’a pas démarré.')
    } finally {
      setIsAgentStarting(false)
    }
  }

  // L’API ne répond qu’après l’arrêt du conteneur vérifié, donc le bouton reste en attente jusque-là.
  async function cancelAgentRun() {
    if (!agentRun || !isActiveAgentRun(agentRun) || isAgentCancelling) return
    setIsAgentCancelling(true)
    setAgentError('')
    const health = resetPollingHealth()
    agentPollingHealthRef.current = health
    setAgentPollingHealth(health)
    setAgentPollingError('')
    try {
      const payload = await apiRequest<unknown>(`/api/agent-runs/${encodeURIComponent(agentRun.run_id)}/cancel`, {
        method: 'POST',
      })
      if (!isAgentRun(payload)) {
        throw new Error('Le backend n’a pas confirmé l’arrêt du run.')
      }
      setAgentRun(payload)
      if (payload.checkpoint_id) {
        await loadAgentChanges(payload.run_id)
      }
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : 'L’annulation OpenHands a échoué.')
    } finally {
      setIsAgentCancelling(false)
    }
  }

  // Accepte explicitement le diff serveur et laisse l’audit SQLite consultable.
  async function acceptAgentChanges() {
    if (!agentRun?.checkpoint_id || isCheckpointTransition) return
    setIsCheckpointTransition(true)
    setAgentError('')
    try {
      await apiRequest<unknown>(`/api/agent-runs/${encodeURIComponent(agentRun.run_id)}/accept`, {
        method: 'POST',
      })
      await loadAgentChanges(agentRun.run_id)
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : 'L’acceptation du checkpoint a échoué.')
    } finally {
      setIsCheckpointTransition(false)
    }
  }

  // Demande une restauration serveur ; le backend refuse tout conflit externe avant écriture.
  async function rollbackAgentChanges() {
    if (!agentRun?.checkpoint_id || isCheckpointTransition) return
    setIsCheckpointTransition(true)
    setAgentError('')
    try {
      await apiRequest<unknown>(`/api/agent-runs/${encodeURIComponent(agentRun.run_id)}/rollback`, {
        method: 'POST',
      })
      await loadAgentChanges(agentRun.run_id)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'La restauration du checkpoint a échoué.'
      // A 409 can have persisted the checkpoint as `conflict`; reload it so
      // stale action buttons are removed before showing the refusal message.
      await loadAgentChanges(agentRun.run_id)
      setAgentError(message)
    } finally {
      setIsCheckpointTransition(false)
    }
  }

  // Recharge la conversation et sa liste après une mutation confirmée par SQLite.
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

  // Un conflit 409 recharge la version SQLite autoritaire au lieu d'écraser l'autre onglet.
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

  // Chemin commun aux envois, modifications, régénérations et réessais.
  // Le message pending reste purement visuel jusqu'à la réponse du backend.
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

  // Valide le brouillon avant de lancer une nouvelle génération normale.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (conversationLoadingLock.current) return
    const submitted = question.trim()
    if (!submitted) {
      setConversationError('Écrivez une question avant de l’envoyer.')
      return
    }
    if (activeProfile && byteLength(submitted) > activeProfile.max_user_message_bytes) {
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

  // Réinitialise seulement l'interface; SQLite attend toujours le premier message.
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
    focusQuestion()
  }

  // Mutations versionnées de la conversation active.
  function handleRename() {
    // Ouvre l'éditeur avec le titre actuellement confirmé par le backend.
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

  // Enregistre le titre avec la révision affichée et recharge en cas de conflit.
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

  // Supprime la conversation confirmée par l'utilisateur sous contrôle de révision.
  async function handleDelete() {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current
    ) return
    // Le backend applique la révision et supprime la conversation avec ses
    // messages. Les souvenirs globaux ne répondent qu'à « Oublie que… ».
    if (!window.confirm(
      `Supprimer définitivement « ${activeConversation.title} » et tous ses messages ?`,
    )) return
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
        focusQuestion()
      }
      await loadConversations(search)
    } catch (error) {
      await handleMutationError(error, navigationRequest, activeConversation.id)
    }
  }

  // Ouvre l'éditeur uniquement pour un message utilisateur encore modifiable.
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

  // Envoie le texte corrigé puis remplace la suite devenue incohérente.
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
    if (activeProfile && byteLength(content) > activeProfile.max_user_message_bytes) {
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

  // Demande une nouvelle réponse à partir de la question associée au message.
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

  // Relance une question échouée sans fabriquer de nouveau tour côté navigateur.
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

  // Copie le texte visible et fournit un retour bref, y compris en cas d'échec.
  async function handleCopy(message: ConversationMessage) {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopyFeedback(`Message ${message.position} copié.`)
    } catch {
      setCopyFeedback('La copie a échoué.')
    }
    window.setTimeout(() => setCopyFeedback(''), 1800)
  }

  // Rendu : le frontend affiche l'état SQLite reçu, sans reconstruire l'historique.
  const activeProfile = modelCatalog ? activeModelProfile(modelCatalog) : null
  const loadingProfile = modelCatalog?.profiles.find(
    (profile) => profile.id === (modelStatus?.loading_profile_id ?? requestedProfileId),
  ) ?? null
  const selectedProfileId = loadingProfile?.id ?? modelStatus?.active_profile_id ?? activeProfile?.id ?? ''
  const agentRunActive = isActiveAgentRun(agentRun)
  const programmingActive = activeProfile?.id === 'development'
  const corePollingTone = coreStatus.state === 'error' ? 'error' : pollingTone(corePollingHealth)
  const coreStatusMessage =
    corePollingTone !== 'normal' && corePollingHealth.message
      ? corePollingHealth.message
      : coreStatus.message
  const modelPresentation = runtimeStatusPresentation(
    loadingProfile?.display_name ?? activeProfile?.display_name ?? null,
    loadingProfile ? 'loading' : modelStatus?.state ?? null,
    modelStatus?.message ?? null,
    modelPollingHealth,
  )
  const agentPollingTone = pollingTone(agentPollingHealth)
  const agentValidation = agentRun ? agentRunValidationPresentation(agentRun) : null
  const modelChangeBlocked = Boolean(
    isModelTransition ||
    isGenerating ||
    coreStatus.state !== 'ready' ||
    !modelStatus ||
    modelStatus.state !== 'ready' ||
    modelStatus.generation_active ||
    modelStatus.agent_run_active ||
    agentRunActive,
  )
  const projectCapabilityActive = Boolean(activeProfile?.capabilities.includes('workspace_projects'))
  return (
    <main>
      <section className="chat" aria-labelledby="page-title">
        <h1 id="page-title">Léa</h1>

        <section className="core-controls" aria-label="Contrôle local de Léa">
          <p className={`core-status status-${corePollingTone}`} aria-live="polite">
            {coreStatusMessage}
          </p>
          {modelCatalog && (
            <div className="model-selector">
              <label htmlFor="model-profile">Profil de Léa</label>
              <select
                id="model-profile"
                value={selectedProfileId}
                onChange={(event) => void handleModelChange(event.target.value)}
                disabled={modelChangeBlocked}
              >
                {modelCatalog.profiles
                  .filter((profile) => profile.enabled)
                  .sort((left, right) => left.display_order - right.display_order)
                  .map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.display_name}
                    </option>
                  ))}
              </select>
              <p
                className={`model-profile-status status-${modelPresentation.tone}`}
                aria-live="polite"
              >
                {modelPresentation.message}
              </p>
              {modelError && (
                <p className="model-profile-status status-error" role="alert">
                  {modelError}
                </p>
              )}
            </div>
          )}
          {!modelCatalog && coreStatus.state === 'ready' && modelError && (
            <p className="model-profile-status status-error" role="alert">
              {modelError}
            </p>
          )}
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

        {projectCapabilityActive && (
          <section className="project-controls" aria-label="Projet de programmation actif">
            <div className="project-header">
              <h2>Projet</h2>
              <button
                type="button"
                className="secondary-button compact-button"
                onClick={() => void refreshProjects()}
                disabled={isProjectTransition || isGenerating || agentRunActive}
              >
                {isProjectTransition ? 'Actualisation…' : 'Actualiser'}
              </button>
            </div>
            {projectCatalog && projectCatalog.projects.length > 0 ? (
              <>
                <label htmlFor="active-project">Projet actif dans IA_WORKSPACE</label>
                <select
                  id="active-project"
                  value={projectCatalog.active_project_id ?? ''}
                  onChange={(event) => void selectProject(event.target.value)}
                  disabled={isProjectTransition || isGenerating || isModelTransition || agentRunActive}
                >
                  <option value="">Sélectionner un projet</option>
                  {projectCatalog.projects.map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>
              </>
            ) : (
              <p className="conversation-empty">Aucun projet dans IA_WORKSPACE.</p>
            )}
            {projectError && (
              <p className="chat-error" role="alert">
                {projectError}
              </p>
            )}
          </section>
        )}

        {programmingActive && (
          <section className="agent-controls" aria-label="Tâche OpenHands">
            <h2>Programmation avec OpenHands</h2>
            <p className="conversation-empty">
              La tâche est exécutée sur le projet actif avec checkpoint avant modification.
            </p>
            <form onSubmit={(event) => void startAgentRun(event)}>
              <label htmlFor="agent-task">Tâche de développement</label>
              <textarea
                id="agent-task"
                value={agentTask}
                onChange={(event) => setAgentTask(event.target.value)}
                placeholder="Décris la correction ou l’évolution à réaliser"
                rows={5}
                disabled={
                  isAgentStarting ||
                  isAgentCancelling ||
                  agentRunActive ||
                  !projectCatalog?.active_project_id ||
                  coreStatus.state !== 'ready'
                }
              />
              <button
                type="submit"
                disabled={
                  isAgentStarting ||
                  isAgentCancelling ||
                  agentRunActive ||
                  !agentTask.trim() ||
                  !projectCatalog?.active_project_id ||
                  coreStatus.state !== 'ready'
                }
              >
                {isAgentStarting ? 'Préparation du checkpoint…' : 'Lancer le run'}
              </button>
            </form>
            {agentRun && (
              <div className="agent-run-status" aria-live="polite">
                <p>
                  <strong>Run :</strong> {agentRun.state}
                </p>
                {agentValidation && (
                  <p className={`agent-run-validation status-${agentValidation.tone}`}>
                    <strong>Validation :</strong> {agentValidation.message}
                  </p>
                )}
                {agentRun.result_summary && <p>{agentRun.result_summary}</p>}
                {agentRunActive && (
                  <button
                    type="button"
                    className="danger-button compact-button"
                    onClick={() => void cancelAgentRun()}
                    disabled={isAgentCancelling}
                  >
                    {isAgentCancelling ? 'Arrêt vérifié en cours…' : 'Annuler le run'}
                  </button>
                )}
                {agentChanges && (
                  <div className="agent-changes">
                    <p>
                      <strong>Checkpoint :</strong> {agentChanges.checkpoint.state}
                    </p>
                    {agentChanges.changes.length > 0 ? (
                      <ul>
                        {agentChanges.changes.map((change) => (
                          <li key={`${change.change}:${change.relative_path}`}>
                            {change.change} — {change.relative_path}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>Aucun fichier modifié par ce run.</p>
                    )}
                    {agentChanges.checkpoint.state === 'completed' && (
                      <div className="editor-actions">
                        {agentValidation?.accepts_changes && (
                          <button
                            type="button"
                            className="compact-button"
                            onClick={() => void acceptAgentChanges()}
                            disabled={isCheckpointTransition}
                          >
                            Accepter les changements
                          </button>
                        )}
                        <button
                          type="button"
                          className="danger-button compact-button"
                          onClick={() => void rollbackAgentChanges()}
                          disabled={isCheckpointTransition}
                        >
                          Restaurer le checkpoint
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
            {agentPollingError && (
              <p className="agent-run-notice status-error" role="alert">
                {agentPollingError}
              </p>
            )}
            {agentPollingTone !== 'normal' && (
              <p
                className={`agent-run-notice status-${agentPollingTone}`}
                role={agentPollingTone === 'error' ? 'alert' : undefined}
              >
                {agentPollingHealth.message}
              </p>
            )}
            {agentError && (
              <p className="chat-error" role="alert">
                {agentError}
              </p>
            )}
          </section>
        )}

        <section className="conversation-browser" aria-label="Conversations locales">
          <label htmlFor="conversation-search">Rechercher une conversation</label>
          <input
            id="conversation-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Titre ou message"
            disabled={coreStatus.state !== 'ready'}
          />
          {isListLoading && (
            <p className="conversation-pending">Chargement des conversations…</p>
          )}
          {!isListLoading && conversations.length === 0 && (
            <p className="conversation-empty">Aucune conversation enregistrée.</p>
          )}
          <div className="conversation-summaries">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                className={
                  conversation.id === activeConversation?.id
                    ? 'conversation-summary active'
                    : 'conversation-summary'
                }
                onClick={() => void loadConversation(conversation.id)}
                disabled={isGenerating}
              >
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
                  <button
                    type="button"
                    className="secondary-button compact-button"
                    onClick={handleRename}
                    disabled={isGenerating || isConversationLoading || isRenaming}
                  >
                    Renommer
                  </button>
                  <button
                    type="button"
                    className="danger-button compact-button"
                    onClick={() => void handleDelete()}
                    disabled={isGenerating || isConversationLoading || isRenaming}
                  >
                    Supprimer
                  </button>
                </>
              )}
              <button
                type="button"
                className="secondary-button compact-button"
                onClick={handleNewConversation}
                disabled={isGenerating || isRenaming}
              >
                Nouvelle conversation
              </button>
            </div>
          </div>

          {activeConversation && renameDraft !== null && (
            <form
              className="inline-editor rename-editor"
              onSubmit={(event) => void handleRenameSubmit(event)}
            >
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
                <button
                  type="submit"
                  className="compact-button"
                  disabled={isRenaming || isGenerating || coreStatus.state !== 'ready'}
                >
                  {isRenaming ? 'Enregistrement…' : 'Enregistrer'}
                </button>
                <button
                  type="button"
                  className="secondary-button compact-button"
                  onClick={() => setRenameDraft(null)}
                  disabled={isRenaming}
                >
                  Annuler
                </button>
              </div>
            </form>
          )}

          {!activeConversation && !pendingText && (
            <p className="conversation-empty">
              La conversation sera enregistrée au premier message.
            </p>
          )}
          {isConversationLoading && <p className="conversation-pending">Chargement…</p>}
          <div className="conversation-list" aria-live="polite">
            {activeConversation?.messages.map((message) => (
              <article
                className={`message message-${message.role} message-${message.status}`}
                key={message.id}
              >
                <strong>{message.role === 'user' ? 'Vous' : 'Léa'}</strong>
                {message.role === 'assistant' && message.profile_id && (
                  <small className="message-profile">
                    {modelCatalog?.profiles.find(
                      (profile) => profile.id === message.profile_id,
                    )?.display_name ?? message.profile_id}
                  </small>
                )}
                {editingMessageId === message.id ? (
                  <form
                    className="inline-editor message-editor"
                    onSubmit={(event) => void handleEditSubmit(event, message)}
                  >
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
                      <button
                        type="submit"
                        className="compact-button"
                        disabled={isGenerating || coreStatus.state !== 'ready'}
                      >
                        {isGenerating ? 'Envoi…' : 'Enregistrer et régénérer'}
                      </button>
                      <button
                        type="button"
                        className="secondary-button compact-button"
                        onClick={() => {
                          setEditingMessageId(null)
                          setEditDraft('')
                        }}
                        disabled={isGenerating}
                      >
                        Annuler
                      </button>
                    </div>
                  </form>
                ) : (
                  <p>{message.content}</p>
                )}
                {message.status === 'failed' && (
                  <p className="message-error">Échec de la génération.</p>
                )}
                {editingMessageId !== message.id && (
                  <div className="message-actions">
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => void handleCopy(message)}
                    >
                      Copier
                    </button>
                    {message.role === 'user' && allowsDestructiveMessageAction(message) && (
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => handleEdit(message)}
                        disabled={isGenerating || isConversationLoading || isRenaming}
                      >
                        Modifier
                      </button>
                    )}
                    {message.role === 'user' &&
                      message.status === 'failed' &&
                      allowsDestructiveMessageAction(message) && (
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => handleRetry(message)}
                          disabled={
                            isGenerating ||
                            isConversationLoading ||
                            isRenaming ||
                            coreStatus.state !== 'ready'
                          }
                        >
                          Réessayer
                        </button>
                      )}
                    {message.role === 'assistant' && allowsDestructiveMessageAction(message) && (
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => handleRegenerate(message)}
                        disabled={
                          isGenerating ||
                          isConversationLoading ||
                          isRenaming ||
                          coreStatus.state !== 'ready'
                        }
                      >
                        Régénérer
                      </button>
                    )}
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
          {copyFeedback && (
            <p className="copy-feedback" aria-live="polite">
              {copyFeedback}
            </p>
          )}
          {conversationError && (
            <p className="chat-error" role="alert">
              {conversationError}
            </p>
          )}
        </section>

        {programmingActive ? (
          <p className="conversation-empty">
            Le profil Programmation utilise la tâche OpenHands ci-dessus, pas la conversation directe.
          </p>
        ) : (
          <form onSubmit={handleSubmit}>
            <label htmlFor="question">Votre question</label>
            <textarea
              ref={questionInput}
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Écrivez votre question"
              rows={5}
              disabled={
                isGenerating ||
                isConversationLoading ||
                isRenaming ||
                coreStatus.state !== 'ready'
              }
            />
            <button
              type="submit"
              disabled={
                isGenerating ||
                isConversationLoading ||
                isRenaming ||
                coreStatus.state !== 'ready'
              }
            >
              {isGenerating ? 'Envoi...' : 'Envoyer'}
            </button>
          </form>
        )}
      </section>
    </main>
  )
}

export default App

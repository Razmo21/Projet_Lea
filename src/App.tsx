import { ApiError, apiRequest } from './lib/api'
import { shortNotice } from './lib/notices'
import Welcome, {
  nextWelcomeIndex,
  welcomePhrases,
  welcomePhrasesForProfile,
} from './components/Welcome'
import { useEphemeralChat } from './hooks/useEphemeralChat'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import {
  allowsDestructiveMessageAction,
  buildSendMessagePayload,
  conversationIdFromSearch,
  createLatestRequestGate,
  isExplicitWebRequest,
  isWebConfirmation,
  isWebFailure,
  messageFailureLabel,
  setConversationInUrl,
  webAuthorizationForTurn,
  webRetryDraft,
} from './lib/conversations'
import type {
  ConversationDetail,
  ConversationMessage,
  ConversationSummary,
} from './lib/conversations'
import {
  activeModelProfile,
  canActivateModel,
  isModelCatalog,
  isModelRuntimeStatus,
} from './lib/models'
import type { ModelCatalog, ModelRuntimeStatus } from './lib/models'
import { isProjectCatalog } from './lib/projects'
import type { ProjectCatalog } from './lib/projects'
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
} from './lib/agentRuns'
import type {
  AgentRun,
  AgentRunChanges,
  PollingHealth,
} from './lib/agentRuns'
import MarkdownMessage from './components/MarkdownMessage'
import AgentRunResult from './components/AgentRunResult'
import WebSources from './components/WebSources'
import Settings from './components/Settings'
import type { SettingsHandle } from './components/Settings'
import ConversationSidebar from './components/ConversationSidebar'
import AutoTextarea from './components/AutoTextarea'
import Icon from './components/Icon'
import { useAppearance } from './hooks/useAppearance'
import ResourcePanel from './components/ResourcePanel'
import { requestPreferences } from './lib/preferences'
import type { Preferences } from './lib/preferences'
import VoiceControls from './components/VoiceControls'
import { appendDictation } from './lib/voice'

type CoreState = 'stopped' | 'starting' | 'ready' | 'stopping' | 'error'

type CoreStatus = {
  state: CoreState
  model: string
  backend: string
  message: string
}

type GenerationResult = 'completed' | 'persisted-error' | 'failed' | 'blocked'

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

// Orchestre l'interface locale sans dupliquer l'état autoritaire du backend.
function App() {
  const { theme, chooseTheme, themeError } = useAppearance()
  const chatScroll = useRef<HTMLDivElement>(null)
  const followMessages = useRef(true)
  const sendButton = useRef<HTMLButtonElement>(null)
  const [voiceControlsHost, setVoiceControlsHost] =
    useState<HTMLDivElement | null>(null)
  const [resourceNoticeHost, setResourceNoticeHost] = useState<HTMLDivElement | null>(null)
  const [alternateNoticeHost, setAlternateNoticeHost] = useState<HTMLDivElement | null>(null)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsPanel = useRef<SettingsHandle>(null)
  const [voiceOpen, setVoiceOpen] = useState(false)
  const voiceRunWaiter = useRef<{
    id: string
    resolve: (run: AgentRun) => void
    reject: (error: Error) => void
  } | null>(null)
  const [preferences, setPreferences] = useState<Preferences | null>(null)
  const [preferencesError, setPreferencesError] = useState('')

  // Relit le réglage persistant au retour ; aucune mesure n'est stockée côté navigateur.
  useEffect(() => {
    if (settingsOpen) return
    let current = true
    void requestPreferences()
      .then((value) => {
        if (current) {
          setPreferences(value)
          setPreferencesError('')
        }
      })
      .catch(() => {
        if (current)
          setPreferencesError(
            'Préférence de ressources indisponible. Ouvre les paramètres pour la vérifier.',
          )
      })
    return () => {
      current = false
    }
  }, [settingsOpen])
  const settingsButton = useRef<HTMLButtonElement>(null)

  // Fermer les paramètres ne recharge ni la conversation ni son brouillon.
  function closeSettings() {
    setSettingsOpen(false)
    setWelcomeIndex(renewedWelcomeIndex)
    window.requestAnimationFrame(() => settingsButton.current?.focus())
  }

  // Le bouton permanent ouvre la page ou lui demande sa fermeture protégée.
  function toggleSettings() {
    if (settingsOpen) settingsPanel.current?.close()
    else setSettingsOpen(true)
  }

  // État visible : brouillon, liste locale, conversation active et éditeurs.
  const [question, setQuestion] = useState('')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeConversation, setActiveConversation] =
    useState<ConversationDetail | null>(null)
  const [coreStatus, setCoreStatus] = useState<CoreStatus>(initialCoreStatus)
  const [modelStatus, setModelStatus] = useState<ModelRuntimeStatus | null>(
    null,
  )
  const ephemeral = useEphemeralChat(
    modelStatus?.instance_id,
    coreStatus.state === 'stopped' || coreStatus.state === 'stopping',
  )
  const normalDraft = useRef('')
  const [welcomeIndex, setWelcomeIndex] = useState(() =>
    Math.floor(Math.random() * welcomePhrases.length),
  )
  const wasEphemeral = useRef(false)
  const displayedConversation = ephemeral.active
    ? ephemeral.conversation
    : activeConversation
  const [search, setSearch] = useState('')
  const [isListLoading, setIsListLoading] = useState(false)
  const [isConversationLoading, setIsConversationLoading] = useState(false)
  const [normalGenerating, setIsGenerating] = useState(false)
  const isGenerating = normalGenerating || ephemeral.sending
  const showSendAction = Boolean(question.trim())
  const responseOperationId = useRef<string | null>(null)
  const responseStopLock = useRef(false)
  const [isResponseStopping, setIsResponseStopping] = useState(false)
  const [pendingText, setPendingText] = useState('')
  const [conversationError, setConversationError] = useState('')
  const [copyFeedback, setCopyFeedback] = useState('')
  const [renameDraft, setRenameDraft] = useState<string | null>(null)
  const [renameTarget, setRenameTarget] = useState<ConversationSummary | null>(null)
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState('')
  const [isRenaming, setIsRenaming] = useState(false)
  const [webInProgress, setWebInProgress] = useState(false)
  const displayedPending = ephemeral.active ? ephemeral.pending : pendingText

  // Le brouillon normal est isolé du texte privé et revient aussi après un arrêt du cœur.
  useEffect(() => {
    if (wasEphemeral.current && !ephemeral.active) {
      setQuestion(normalDraft.current)
      setWelcomeIndex(renewedWelcomeIndex)
    }
    wasEphemeral.current = ephemeral.active
  }, [ephemeral.active])

  // Une nouvelle conversation revient au bas ; les autres mises à jour respectent la lecture.
  useEffect(() => {
    followMessages.current = true
  }, [displayedConversation?.id])
  useEffect(() => {
    if (renameDraft !== null) {
      chatScroll.current?.scrollTo({ top: 0 })
      return
    }
    if (followMessages.current && !settingsOpen && !voiceOpen) {
      chatScroll.current?.scrollTo({ top: chatScroll.current.scrollHeight })
    }
  }, [
    displayedConversation,
    displayedPending,
    isGenerating,
    settingsOpen,
    voiceOpen,
    renameDraft,
  ])

  // Verrous synchrones : ils bloquent les doubles clics avant le prochain rendu React.
  const generationLock = useRef(false)
  const renameLock = useRef(false)
  const listRequestNumber = useRef(0)
  const conversationRequests = useRef(createLatestRequestGate())
  const conversationLoadingLock = useRef(false)
  const questionInput = useRef<HTMLTextAreaElement>(null)
  const activeConversationRef = useRef<ConversationDetail | null>(null)
  const [corePollingHealth, setCorePollingHealth] =
    useState<PollingHealth>(resetPollingHealth)
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog | null>(null)
  const [modelError, setModelError] = useState('')
  const [modelPollingHealth, setModelPollingHealth] =
    useState<PollingHealth>(resetPollingHealth)
  const [requestedProfileId, setRequestedProfileId] = useState<string | null>(
    null,
  )
  const [isModelTransition, setIsModelTransition] = useState(false)
  const [projectCatalog, setProjectCatalog] = useState<ProjectCatalog | null>(
    null,
  )
  const [projectError, setProjectError] = useState('')
  const [isProjectTransition, setIsProjectTransition] = useState(false)
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null)
  const [agentChanges, setAgentChanges] = useState<AgentRunChanges | null>(null)
  const [agentError, setAgentError] = useState('')
  const [agentPollingError, setAgentPollingError] = useState('')
  const [agentPollingHealth, setAgentPollingHealth] =
    useState<PollingHealth>(resetPollingHealth)
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
  const agentSelectionRequest = useRef(0)
  const agentStartLock = useRef(false)
  const agentStopRequested = useRef(false)

  // Le bouton reste en attente jusqu'à la fin effective de la requête ou du run.
  useEffect(() => {
    if (!isGenerating && !isAgentStarting && !isActiveAgentRun(agentRun)) {
      responseStopLock.current = false
      setIsResponseStopping(false)
    }
  }, [isGenerating, isAgentStarting, agentRun?.state])

  // Ferme ensemble les deux éditeurs afin d'éviter des brouillons attachés à une autre conversation.
  const closeEditors = useCallback(() => {
    setRenameDraft(null)
    setRenameTarget(null)
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
      const controllerResponse = await fetch('/api/core/status', {
        cache: 'no-store',
      })
      const status = await readCoreStatus(controllerResponse)
      // A timed-out health probe is not a confirmed stop. Reuse the existing
      // consecutive-failure policy before clearing the frozen vocal context.
      // Explicit stopped/starting states and user stop actions remain immediate.
      if (status.state === 'error') throw new Error(status.message)
      if (!modelTransitionLock.current) {
        const health = resetPollingHealth()
        corePollingHealthRef.current = health
        setCorePollingHealth(health)
        setCoreStatus(status)
      }
    } catch (failure) {
      if (!modelTransitionLock.current) {
        const health = recordPollingFailure(
          corePollingHealthRef.current,
          failure instanceof Error
            ? failure.message
            : 'Le contrôleur local de Léa n’est pas disponible.',
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
      setModelError(
        error instanceof Error
          ? error.message
          : 'Catalogue des profils indisponible.',
      )
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
      const message =
        error instanceof Error ? error.message : 'État du modèle indisponible.'
      const health = recordPollingFailure(
        modelPollingHealthRef.current,
        message,
      )
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
      setProjectError(
        error instanceof Error
          ? error.message
          : 'Registre des projets indisponible.',
      )
      return null
    }
  }, [])

  // Lit le diff calculé par le backend ; React ne reconstitue jamais de snapshot local.
  const loadAgentChanges = useCallback(async (runId: string) => {
    const selection = agentSelectionRequest.current
    try {
      const payload = await apiRequest<unknown>(
        `/api/agent-runs/${encodeURIComponent(runId)}/changes`,
      )
      if (selection !== agentSelectionRequest.current) return null
      if (!isAgentRunChanges(payload)) {
        throw new Error('Le checkpoint du run est invalide.')
      }
      setAgentChanges(payload)
      setAgentError('')
      return payload
    } catch (error) {
      if (selection !== agentSelectionRequest.current) return null
      setAgentChanges(null)
      setAgentError(
        error instanceof Error
          ? error.message
          : 'Les changements du run sont indisponibles.',
      )
      return null
    }
  }, [])

  // Résout le run de la conversation sélectionnée ; les anciens runs sans
  // conversation restent consultables par projet, sans être dupliqués dans SQLite.
  const loadLatestAgentRun = useCallback(
    async (projectId: string | null, conversationRunId: string | null = null) => {
      const request = ++agentSelectionRequest.current
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
        const payload = await apiRequest<unknown>(
          conversationRunId
            ? `/api/agent-runs/${encodeURIComponent(conversationRunId)}`
            : '/api/agent-runs',
        )
        if (request !== agentSelectionRequest.current) return null
        if (conversationRunId ? !isAgentRun(payload) : !isAgentRunList(payload)) {
          throw new Error('La liste des runs OpenHands est invalide.')
        }
        const health = resetPollingHealth()
        agentPollingHealthRef.current = health
        setAgentPollingHealth(health)
        setAgentPollingError('')
        setAgentError('')
        const candidate = isAgentRun(payload)
          ? payload
          : isAgentRunList(payload)
            ? latestAgentRunForProject(payload.runs, projectId)
            : null
        const latest = candidate?.project_id === projectId ? candidate : null
        setAgentRun(latest)
        setAgentChanges(null)
        if (latest?.checkpoint_id && !isActiveAgentRun(latest)) {
          await loadAgentChanges(latest.run_id)
        }
        return latest
      } catch (error) {
        if (request !== agentSelectionRequest.current) return null
        setAgentError(
          error instanceof Error
            ? error.message
            : 'Les runs OpenHands sont indisponibles.',
        )
        return null
      }
    },
    [loadAgentChanges],
  )

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
        setConversationError(
          error instanceof Error ? error.message : 'Liste indisponible.',
        )
      }
    } finally {
      if (requestNumber === listRequestNumber.current) {
        setIsListLoading(false)
      }
    }
  }, [])

  // Charge une conversation seulement si aucune navigation plus récente n'a pris sa place.
  const loadConversation = useCallback(
    async (conversationId: string, updateUrl = true) => {
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
          setConversationError(
            error instanceof Error
              ? error.message
              : 'Conversation indisponible.',
          )
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
    },
    [closeEditors],
  )

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
        conversationIdFromSearch(window.location.search) ??
        activeConversationRef.current?.id
      if (requestedConversation) {
        void loadConversation(requestedConversation, false)
      }
    }
    previousCoreState.current = coreStatus.state
  }, [
    coreStatus.state,
    loadConversation,
    loadConversations,
    loadModelCatalog,
    refreshModelStatus,
    search,
  ])

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
    if (
      coreStatus.state === 'ready' &&
      profile?.capabilities.includes('workspace_projects')
    ) {
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

  const selectedConversationRunId = activeConversation?.messages
    .slice()
    .reverse()
    .find((message) => message.agent_run_id)?.agent_run_id ?? null

  // Retrouve le checkpoint du tour sélectionné, même après rechargement de la page.
  useEffect(() => {
    const profile = modelCatalog ? activeModelProfile(modelCatalog) : null
    if (
      coreStatus.state === 'ready' &&
      profile?.capabilities.includes('workspace_projects')
    ) {
      void loadLatestAgentRun(
        projectCatalog?.active_project_id ?? null,
        selectedConversationRunId,
      )
    }
  }, [
    coreStatus.state,
    loadLatestAgentRun,
    modelCatalog,
    projectCatalog?.active_project_id,
    selectedConversationRunId,
  ])

  // Suit le run courant jusqu'à sa fin et arrête le polling au démontage de l'effet.
  useEffect(() => {
    const activeRunId = agentRun?.run_id
    if (!activeRunId || !isActiveAgentRun(agentRun)) return
    let cancelled = false
    // Ignore toute réponse arrivée après le démontage de cet effet de polling.
    const refreshRun = async () => {
      try {
        const payload = await apiRequest<unknown>(
          `/api/agent-runs/${encodeURIComponent(activeRunId)}`,
        )
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
        if (
          !isActiveAgentRun(run) &&
          run.conversation_id === activeConversationRef.current?.id
        ) {
          void loadConversation(run.conversation_id, false)
        }
        if (!isActiveAgentRun(run) && run.checkpoint_id) {
          await loadAgentChanges(run.run_id)
        }
        if (!isActiveAgentRun(run)) void loadConversations(search)
      } catch (error) {
        if (!cancelled) {
          const message =
            error instanceof Error
              ? error.message
              : 'Le statut du run OpenHands est indisponible.'
          const health = recordPollingFailure(
            agentPollingHealthRef.current,
            message,
          )
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
    // Une nouvelle représentation du même run ne doit pas relancer la requête
    // immédiate de cet effet : seuls son identité ou son état changent le suivi.
  }, [agentRun?.run_id, agentRun?.state, loadAgentChanges])

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
        message:
          error instanceof Error
            ? error.message
            : 'L’opération sur Léa a échoué.',
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
    )
      return

    modelTransitionLock.current = true
    setIsModelTransition(true)
    setRequestedProfileId(profileId)
    setModelError('')
    const health = resetPollingHealth()
    modelPollingHealthRef.current = health
    setModelPollingHealth(health)
    setModelStatus(
      (current) =>
        current && {
          ...current,
          state: 'loading',
          loading_profile_id: profileId,
          message: 'Chargement du profil sélectionné…',
        },
    )
    try {
      const activated = await apiRequest<unknown>(
        `/api/models/${encodeURIComponent(profileId)}/activate`,
        {
          method: 'POST',
        },
      )
      if (!isModelRuntimeStatus(activated)) {
        throw new Error('Le backend n’a pas confirmé le nouveau profil.')
      }
      setModelStatus(activated)
      setWelcomeIndex(Math.floor(Math.random() * welcomePhrasesForProfile(profileId).length))
      setModelError('')
      await loadModelCatalog()
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'Le changement de profil a échoué.'
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
    if (projectTransitionLock.current || isProjectTransition || isGenerating)
      return
    projectTransitionLock.current = true
    setIsProjectTransition(true)
    setProjectError('')
    try {
      const catalog = await apiRequest<unknown>('/api/projects/refresh', {
        method: 'POST',
      })
      if (!isProjectCatalog(catalog)) {
        throw new Error(
          'Le backend n’a pas confirmé l’actualisation des projets.',
        )
      }
      setProjectCatalog(catalog)
    } catch (error) {
      setProjectError(
        error instanceof Error
          ? error.message
          : 'Actualisation des projets échouée.',
      )
    } finally {
      projectTransitionLock.current = false
      setIsProjectTransition(false)
    }
  }

  // Active un projet par UUID public sans jamais envoyer de chemin depuis le navigateur.
  async function selectProject(projectId: string) {
    if (
      !projectId ||
      projectTransitionLock.current ||
      isProjectTransition ||
      isGenerating
    )
      return
    projectTransitionLock.current = true
    setIsProjectTransition(true)
    setProjectError('')
    try {
      const catalog = await apiRequest<unknown>(
        `/api/projects/${encodeURIComponent(projectId)}/activate`,
        {
          method: 'POST',
        },
      )
      if (!isProjectCatalog(catalog)) {
        throw new Error('Le backend n’a pas confirmé le projet actif.')
      }
      setProjectCatalog(catalog)
    } catch (error) {
      setProjectError(
        error instanceof Error ? error.message : 'Sélection du projet échouée.',
      )
      await loadProjects()
    } finally {
      projectTransitionLock.current = false
      setIsProjectTransition(false)
    }
  }

  // Démarre un seul run backend depuis la saisie commune ; le chemin ne vient jamais du navigateur.
  async function startAgentRun() {
    const task = question.trim()
    if (
      !task ||
      agentStartLock.current ||
      isAgentStarting ||
      isActiveAgentRun(agentRun) ||
      coreStatus.state !== 'ready' ||
      modelStatus?.active_profile_id !== 'development' ||
      !projectCatalog?.active_project_id
    )
      return
    if (
      activeProfile &&
      byteLength(task) > activeProfile.max_user_message_bytes
    ) {
      setAgentError('La tâche est trop longue pour le profil Programmation.')
      return
    }
    agentStartLock.current = true
    agentSelectionRequest.current += 1
    setIsAgentStarting(true)
    setAgentError('')
    setConversationError('')
    const health = resetPollingHealth()
    agentPollingHealthRef.current = health
    setAgentPollingHealth(health)
    setAgentPollingError('')
    setAgentChanges(null)
    setPendingText(task)
    setQuestion('')
    try {
      const payload = await apiRequest<unknown>('/api/agent-runs', {
        method: 'POST',
        body: JSON.stringify({
          task,
          record_conversation: true,
          conversation_id: activeConversation?.id ?? null,
          expected_revision: activeConversation?.revision ?? null,
          expected_profile_id: activeProfile?.id,
          expected_project_id: projectCatalog.active_project_id,
        }),
      })
      if (!isAgentRun(payload)) {
        throw new Error('Le backend n’a pas confirmé le run OpenHands.')
      }
      setAgentRun(payload)
      if (payload.conversation_id) await loadConversation(payload.conversation_id)
      setPendingText('')
      await loadConversations(search)
      // Un clic pendant la création du checkpoint attend l'identité réelle du run.
      if (agentStopRequested.current) await cancelAgentRun(payload)
    } catch (error) {
      setQuestion(task)
      setAgentError(
        error instanceof Error
          ? error.message
          : 'Le run OpenHands n’a pas démarré.',
      )
    } finally {
      agentStartLock.current = false
      agentStopRequested.current = false
      responseStopLock.current = false
      setIsResponseStopping(false)
      setPendingText('')
      setIsAgentStarting(false)
    }
  }

  // L’API ne répond qu’après l’arrêt du conteneur vérifié, donc le bouton reste en attente jusque-là.
  async function cancelAgentRun(target = agentRun) {
    if (!target || !isActiveAgentRun(target) || isAgentCancelling) return
    setIsAgentCancelling(true)
    setAgentError('')
    const health = resetPollingHealth()
    agentPollingHealthRef.current = health
    setAgentPollingHealth(health)
    setAgentPollingError('')
    try {
      const payload = await apiRequest<unknown>(
        `/api/agent-runs/${encodeURIComponent(target.run_id)}/cancel`,
        {
          method: 'POST',
        },
      )
      if (!isAgentRun(payload)) {
        throw new Error('Le backend n’a pas confirmé l’arrêt du run.')
      }
      setAgentRun(payload)
      if (payload.checkpoint_id) {
        await loadAgentChanges(payload.run_id)
      }
      // L'annulation termine aussi le tour SQLite. Relire sa révision avant
      // d'autoriser la tâche suivante évite de renvoyer une révision périmée.
      if (payload.conversation_id === activeConversationRef.current?.id) {
        await loadConversation(payload.conversation_id, false)
      }
      await loadConversations(search)
    } catch (error) {
      setAgentError(
        error instanceof Error
          ? error.message
          : 'L’annulation OpenHands a échoué.',
      )
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
      await apiRequest<unknown>(
        `/api/agent-runs/${encodeURIComponent(agentRun.run_id)}/accept`,
        {
          method: 'POST',
        },
      )
      await loadAgentChanges(agentRun.run_id)
    } catch (error) {
      setAgentError(
        error instanceof Error
          ? error.message
          : 'L’acceptation du checkpoint a échoué.',
      )
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
      await apiRequest<unknown>(
        `/api/agent-runs/${encodeURIComponent(agentRun.run_id)}/rollback`,
        {
          method: 'POST',
        },
      )
      await loadAgentChanges(agentRun.run_id)
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'La restauration du checkpoint a échoué.'
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
    } else if (
      error instanceof ApiError &&
      error.status === 409 &&
      conversationId
    ) {
      const reloadRequest = await loadConversation(conversationId, false)
      await loadConversations(search)
      if (!conversationRequests.current.isCurrent(reloadRequest)) {
        return
      }
      activeRequest = reloadRequest
    }
    if (conversationRequests.current.isCurrent(activeRequest)) {
      setConversationError(
        error instanceof Error ? error.message : 'L’opération a échoué.',
      )
    }
  }

  // Chemin commun aux envois, modifications et réessais.
  // Le message pending reste purement visuel jusqu'à la réponse du backend.
  async function runGeneration(
    operation: (responseId: string) => Promise<ConversationDetail>,
    pending = '',
    clearDraft = true,
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
    const responseId = crypto.randomUUID()
    responseOperationId.current = responseId
    const navigationRequest = conversationRequests.current.current()
    const submittedDraft = clearDraft && pending ? question : null
    setIsGenerating(true)
    setPendingText(pending)
    setConversationError('')
    // La bulle d'attente montre le texte envoyé ; le champ redevient vide immédiatement.
    if (submittedDraft !== null) setQuestion('')
    let responseReceived = false
    try {
      const conversation = await operation(responseId)
      responseReceived = true
      await refreshAfterMutation(conversation, navigationRequest)
      if (
        clearDraft &&
        conversationRequests.current.isCurrent(navigationRequest)
      ) {
        setQuestion('')
      }
      return 'completed'
    } catch (error) {
      // Un refus sans tour enregistré restitue le brouillon, uniquement dans sa conversation.
      if (
        submittedDraft !== null &&
        !responseReceived &&
        conversationRequests.current.isCurrent(navigationRequest) &&
        (!(error instanceof ApiError) ||
          !error.conversation ||
          (error.status === 409 && error.conversation.messages.at(-1)?.error !== 'interrupted'))
      ) {
        setQuestion(submittedDraft)
      }
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
      responseOperationId.current = null
      responseStopLock.current = false
      setIsResponseStopping(false)
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
    if (
      activeProfile &&
      byteLength(submitted) > activeProfile.max_user_message_bytes
    ) {
      setConversationError(
        'La question est trop longue pour le contexte actif de Léa.',
      )
      return
    }
    if (programmingActive) {
      void startAgentRun()
      return
    }
    if (ephemeral.active) {
      if (isGenerating || ephemeral.busy || coreStatus.state !== 'ready') return
      const draft = question
      setQuestion('')
      void ephemeral.send(submitted).catch(() => {
        // Les erreurs restent dans le mode temporaire, jamais dans l'historique normal.
        if (wasEphemeral.current) setQuestion(draft)
      })
      return
    }
    const confirmsPendingWeb =
      activeConversation?.web_confirmation_pending === true &&
      isWebConfirmation(submitted)
    const usesWeb = webAuthorizationForTurn(submitted) || confirmsPendingWeb
    const operationId = usesWeb ? crypto.randomUUID() : null
    const payload = {
      // Le texte explicite ou la confirmation liée au tour constituent les
      // seules autorisations ; le réglage global n'est jamais une permission.
      ...buildSendMessagePayload(activeConversation, submitted),
      ...(operationId ? { web_request_id: operationId } : {}),
    }
    setWebInProgress(usesWeb)
    void runGeneration(
      (responseId) =>
        apiRequest<ConversationDetail>('/api/conversations/messages', {
          method: 'POST',
          headers: { 'X-Lea-Response-ID': responseId },
          body: JSON.stringify(payload),
        }),
      submitted,
    ).finally(() => {
      setWebInProgress(false)
    })
  }

  // Entrée emprunte le même bouton et ses barrières ; Maj+Entrée et une composition
  // IME restent de la saisie. Maintenir la touche ne doit pas envoyer plusieurs tours.
  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key !== 'Enter' ||
      event.shiftKey ||
      event.nativeEvent.isComposing ||
      event.nativeEvent.keyCode === 229
    )
      return
    event.preventDefault()
    if (event.repeat || !sendButton.current || sendButton.current.disabled)
      return
    event.currentTarget.form?.requestSubmit(sendButton.current)
  }

  // Le bouton arrête l'activité exacte, sans éteindre Léa ni libérer prématurément le modèle.
  async function stopResponse() {
    if (responseStopLock.current || isAgentCancelling) return
    responseStopLock.current = true
    setIsResponseStopping(true)
    if (isAgentStarting) {
      agentStopRequested.current = true
      return
    }
    try {
      if (isActiveAgentRun(agentRun)) {
        await cancelAgentRun()
        responseStopLock.current = false
        setIsResponseStopping(false)
      }
      else if (ephemeral.sending) await ephemeral.cancel()
      else if (responseOperationId.current) {
        await apiRequest(`/api/responses/${responseOperationId.current}/cancel`, {
          method: 'POST',
        })
      }
    } catch (error) {
      responseStopLock.current = false
      setIsResponseStopping(false)
      setConversationError(
        error instanceof Error
          ? error.message
          : 'L’arrêt de la réponse n’a pas été confirmé.',
      )
    }
  }

  // Réinitialise seulement l'interface; SQLite attend toujours le premier message.
  function handleNewConversation() {
    if (
      isGenerating || renameLock.current || isAgentStarting ||
      agentRunActive || isCheckpointTransition
    ) return
    setWelcomeIndex(renewedWelcomeIndex)
    conversationRequests.current.invalidate()
    conversationLoadingLock.current = false
    setIsConversationLoading(false)
    setActiveConversation(null)
    closeEditors()
    setQuestion('')
    setPendingText('')
    setConversationError('')
    setConversationInUrl(null)
    if (programmingActive) {
      agentSelectionRequest.current += 1
      setAgentRun(null)
      setAgentChanges(null)
    }
    focusQuestion()
  }

  // Ouvre le renommage depuis les métadonnées de la barre latérale.
  function openRename(conversationId: string) {
    // Les métadonnées suffisent : le crayon n'ouvre pas une conversation verrouillée.
    const target = conversations.find((conversation) => conversation.id === conversationId)
    if (!target || target.generation_active || renameLock.current) return
    setRenameTarget(target)
    setRenameDraft(target.title)
    setConversationError('')
  }

  // Renomme la ligne choisie sans changer la conversation ni son brouillon.
  async function handleRenameSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      !renameTarget ||
      renameDraft === null ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current
    )
      return
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
      const conversation = await apiRequest<ConversationSummary>(
        `/api/conversations/${renameTarget.id}`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            title,
            expected_revision: renameTarget.revision,
          }),
        },
      )
      setActiveConversation((current) => current?.id === conversation.id
        ? { ...current, title: conversation.title, revision: conversation.revision }
        : current)
      await loadConversations(search)
      if (conversationRequests.current.isCurrent(navigationRequest)) {
        setRenameDraft(null)
        setRenameTarget(null)
      }
    } catch (error) {
      setConversationError(error instanceof Error ? error.message : 'Le renommage a échoué.')
      await loadConversations(search)
      if (error instanceof ApiError && error.status === 409) {
        setRenameDraft(null)
        setRenameTarget(null)
      }
    } finally {
      renameLock.current = false
      setIsRenaming(false)
    }
  }

  // Supprime la conversation confirmée par l'utilisateur sous contrôle de révision.
  async function handleDelete(
    target: ConversationSummary | null = activeConversation,
  ) {
    if (
      !target ||
      target.generation_active ||
      coreStatus.state !== 'ready' ||
      isGenerating ||
      conversationLoadingLock.current ||
      renameLock.current
    )
      return
    // Le backend applique la révision et supprime la conversation avec ses
    // messages. Les souvenirs globaux ne répondent qu'à « Oublie que… ».
    if (
      !window.confirm(
        `Supprimer définitivement « ${target.title} » et tous ses messages ?`,
      )
    )
      return
    const navigationRequest = conversationRequests.current.current()
    renameLock.current = true
    setIsRenaming(true)
    setConversationError('')
    let clearedSelection = false
    try {
      await apiRequest<void>(`/api/conversations/${target.id}`, {
        method: 'DELETE',
        body: JSON.stringify({
          expected_revision: target.revision,
        }),
      })
      // Supprimer une autre ligne de la barre ne change ni la sélection ni le brouillon.
      if (
        conversationRequests.current.isCurrent(navigationRequest) &&
        activeConversationRef.current?.id === target.id
      ) {
        conversationRequests.current.invalidate()
        conversationLoadingLock.current = false
        setIsConversationLoading(false)
        setActiveConversation(null)
        closeEditors()
        setConversationInUrl(null)
        setConversationError('')
        clearedSelection = true
      }
      await loadConversations(search)
    } catch (error) {
      if (activeConversationRef.current?.id === target.id) {
        await handleMutationError(error, navigationRequest, target.id)
      } else {
        setConversationError(
          error instanceof Error ? error.message : 'La suppression a échoué.',
        )
        await loadConversations(search)
      }
    } finally {
      renameLock.current = false
      setIsRenaming(false)
      if (clearedSelection) focusQuestion()
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
      isWebFailure(message) ||
      !allowsDestructiveMessageAction(message)
    )
      return
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
      isWebFailure(message) ||
      !allowsDestructiveMessageAction(message)
    )
      return
    const content = editDraft.trim()
    if (!content) {
      setConversationError('Le message ne peut pas être vide.')
      return
    }
    if (
      activeProfile &&
      byteLength(content) > activeProfile.max_user_message_bytes
    ) {
      setConversationError(
        'Le message est trop long pour le contexte actif de Léa.',
      )
      return
    }
    const result = await runGeneration((responseId) =>
      apiRequest<ConversationDetail>(
        `/api/conversations/${activeConversation.id}/messages/${message.id}`,
        {
          method: 'PATCH',
          headers: { 'X-Lea-Response-ID': responseId },
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

  // Relance une question échouée sans fabriquer de nouveau tour côté navigateur.
  function handleRetry(message: ConversationMessage) {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      message.role !== 'user' ||
      !allowsDestructiveMessageAction(message)
    )
      return
    void runGeneration((responseId) =>
      apiRequest<ConversationDetail>(
        `/api/conversations/${activeConversation.id}/messages/${message.id}/retry`,
        {
          method: 'POST',
          headers: { 'X-Lea-Response-ID': responseId },
          body: JSON.stringify({
            expected_revision: activeConversation.revision,
          }),
        },
      ),
    )
  }

  // Prépare une nouvelle conversation Web sans recycler le tour ni son ancien accord.
  function prepareWebRetry(message: ConversationMessage) {
    if (
      !activeConversation ||
      isGenerating ||
      conversationLoadingLock.current ||
      message.role !== 'user' ||
      !isWebFailure(message) ||
      preferences?.web_enabled !== true
    )
      return
    conversationRequests.current.invalidate()
    conversationLoadingLock.current = false
    setIsConversationLoading(false)
    setActiveConversation(null)
    closeEditors()
    setQuestion(webRetryDraft(message, activeConversation.messages))
    setPendingText('')
    setConversationError('')
    setConversationInUrl(null)
    focusQuestion()
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

  // Le titre change seulement au retour à l'accueil et reste propre au profil courant.
  function renewedWelcomeIndex(current: number) {
    return nextWelcomeIndex(current, welcomePhrasesForProfile(activeProfile?.id).length)
  }
  const loadingProfile =
    modelCatalog?.profiles.find(
      (profile) =>
        profile.id === (modelStatus?.loading_profile_id ?? requestedProfileId),
    ) ?? null
  const selectedProfileId =
    loadingProfile?.id ??
    modelStatus?.active_profile_id ??
    activeProfile?.id ??
    ''
  const agentRunActive = isActiveAgentRun(agentRun)
  const programmingActive = activeProfile?.id === 'development'
  const programmingReady = programmingActive && coreStatus.state === 'ready' &&
    modelStatus?.state === 'ready' && !isModelTransition

  // Une bascule retire aussi le contenu déjà ouvert, sans effacer son historique.
  useEffect(() => {
    if (modelCatalog && modelStatus && !programmingReady && activeConversation?.has_agent_runs) {
      conversationRequests.current.invalidate()
      setActiveConversation(null)
      setConversationInUrl(null, true)
      closeEditors()
    }
  }, [programmingReady, modelCatalog, modelStatus, activeConversation?.has_agent_runs, closeEditors])
  const showResourceChart =
    !settingsOpen && !voiceOpen && preferences?.show_resource_chart === true
  const corePollingTone =
    coreStatus.state === 'error' ? 'error' : pollingTone(corePollingHealth)
  const coreStatusMessage =
    corePollingTone !== 'normal' && corePollingHealth.message
      ? corePollingHealth.message
      : coreStatus.message
  // L'état normal est déjà porté par les boutons ; seules les alertes et
  // transitions occupent le bandeau supérieur, également dans les autres vues.
  const coreNotice =
    corePollingTone !== 'normal' ||
    coreStatus.state === 'starting' ||
    coreStatus.state === 'stopping' ? (
      <p
        className={`core-status status-${corePollingTone}`}
        role={corePollingTone === 'error' ? 'alert' : 'status'}
      >
        {shortNotice(coreStatusMessage, 'core')}
      </p>
    ) : null
  const modelPresentation = runtimeStatusPresentation(
    loadingProfile?.display_name ?? activeProfile?.display_name ?? null,
    loadingProfile ? 'loading' : (modelStatus?.state ?? null),
    modelStatus?.message ?? null,
    modelPollingHealth,
  )
  const agentPollingTone = pollingTone(agentPollingHealth)
  const agentValidation = agentRun
    ? agentRunValidationPresentation(agentRun)
    : null
  const modelChangeBlocked = Boolean(
    ephemeral.active ||
      ephemeral.busy ||
      isAgentStarting ||
      isCheckpointTransition ||
      isModelTransition ||
      isGenerating ||
      coreStatus.state !== 'ready' ||
      !modelStatus ||
      modelStatus.state !== 'ready' ||
      modelStatus.generation_active ||
      modelStatus.agent_run_active ||
      agentRunActive,
  )
  const projectCapabilityActive = Boolean(
    activeProfile?.capabilities.includes('workspace_projects'),
  )

  // La voix utilise le suivi OpenHands existant, sans seconde boucle de polling.
  useEffect(() => {
    const waiting = voiceRunWaiter.current
    if (!waiting) return
    if (agentRun?.run_id === waiting.id && !isActiveAgentRun(agentRun)) {
      waiting.resolve(agentRun)
    } else if (agentPollingHealth.consecutive_failures >= 3) {
      waiting.reject(
        new Error(
          'Suivi OpenHands indisponible. Vérifie le run dans l’interface classique avant toute nouvelle demande.',
        ),
      )
    }
  }, [agentRun, agentPollingHealth])

  // La dictée alimente toujours la saisie visible, y compris la tâche Programmation.
  function dictated(text: string) {
    if (activeConversationRef.current?.id !== activeConversation?.id) {
      throw new Error('La conversation a changé ; dictée non insérée.')
    }
    setQuestion((draft) => appendDictation(draft, text))
  }

  // La voix change l'entrée et la sortie ; les endpoints existants gardent les permissions et la persistance.
  async function sendVoice(
    text: string,
    signal: AbortSignal,
  ): Promise<{ text: string; review?: boolean; notice?: string }> {
    if (
      signal.aborted ||
      !activeProfile ||
      coreStatus.state !== 'ready' ||
      activeConversationRef.current?.id !== activeConversation?.id
    ) {
      throw new Error('Le contexte a changé. Recommence l’intervention.')
    }
    if (byteLength(text) > activeProfile.max_user_message_bytes) {
      throw new Error('La transcription est trop longue pour le profil actif.')
    }
    if (ephemeral.active) return { text: await ephemeral.send(text, signal) }
    if (activeProfile.capabilities.includes('agent_runs')) {
      if (!projectCatalog?.active_project_id || isActiveAgentRun(agentRun)) {
        throw new Error(
          'Sélectionne un projet et termine le run actif dans l’interface classique.',
        )
      }
      setIsAgentStarting(true)
      setAgentChanges(null)
      let run: AgentRun
      try {
        run = requireAgentRun(
          await apiRequest('/api/agent-runs', {
            method: 'POST',
            body: JSON.stringify({
              task: text,
              record_conversation: true,
              conversation_id: activeConversation?.id ?? null,
              expected_revision: activeConversation?.revision ?? null,
              expected_profile_id: activeProfile.id,
              expected_project_id: projectCatalog.active_project_id,
            }),
          }),
        )
        setAgentRun(run)
        if (run.conversation_id)
          await loadConversation(run.conversation_id, true)
        await loadConversations(search)
        if (agentStopRequested.current) {
          await cancelAgentRun(run)
          run = requireAgentRun(await apiRequest(`/api/agent-runs/${run.run_id}`))
        }
      } finally {
        agentStopRequested.current = false
        setIsAgentStarting(false)
      }
      // Fermer l'audio n'annule pas silencieusement une mutation de projet déjà autorisée.
      if (signal.aborted)
        throw new Error(
          'Audio fermé. Le run reste consultable dans Programmation.',
        )
      const finished = await new Promise<AgentRun>((resolve, reject) => {
        if (!isActiveAgentRun(run)) {
          resolve(run)
          return
        }
        const cancel = () =>
          reject(new Error('Audio fermé ; consulte le run dans Programmation.'))
        signal.addEventListener('abort', cancel, { once: true })
        voiceRunWaiter.current = {
          id: run.run_id,
          resolve: (value) => {
            signal.removeEventListener('abort', cancel)
            resolve(value)
          },
          reject: (error) => {
            signal.removeEventListener('abort', cancel)
            reject(error)
          },
        }
        // Un run court peut finir pendant le chargement de sa conversation.
        // Un instantané couvre cette course ; la suite utilise le poller existant.
        void apiRequest<unknown>(`/api/agent-runs/${run.run_id}`, { signal })
          .then((payload) => {
            const current = requireAgentRun(payload)
            if (
              !isActiveAgentRun(current) &&
              voiceRunWaiter.current?.id === run.run_id
            ) {
              voiceRunWaiter.current.resolve(current)
            }
          })
          .catch((failure: unknown) => {
            if (voiceRunWaiter.current?.id === run.run_id) {
              voiceRunWaiter.current.reject(
                failure instanceof Error
                  ? failure
                  : new Error('Suivi du run indisponible.'),
              )
            }
          })
      }).finally(() => {
        voiceRunWaiter.current = null
      })
      const detail = finished.conversation_id
        ? await apiRequest<ConversationDetail>(
            `/api/conversations/${finished.conversation_id}`,
          )
        : null
      if (detail)
        await refreshAfterMutation(
          detail,
          conversationRequests.current.current(),
        )
      const answer = detail?.messages.find(
        (item) =>
          item.agent_run_id === finished.run_id && item.role === 'assistant',
      )?.content
      return {
        text:
          answer ??
          `Run ${finished.state}, validation ${finished.validation_status}. Examine le résultat dans l’interface classique.`,
        review: true,
        notice: finished.state === 'completed'
          ? agentRunValidationPresentation(finished).message
          : finished.state === 'cancelled' ? 'Tâche annulée' : 'Tâche non terminée',
      }
    }
    const explicitVoiceWeb = isExplicitWebRequest(text)
    const confirmsPendingVoiceWeb =
      activeConversation?.web_confirmation_pending === true &&
      isWebConfirmation(text)
    let answer = ''
    const voiceWebOperationId =
      explicitVoiceWeb || confirmsPendingVoiceWeb ? crypto.randomUUID() : null
    const cancelVoiceWeb = () => {
      if (voiceWebOperationId) {
        void apiRequest(`/api/web/operations/${voiceWebOperationId}/cancel`, {
          method: 'POST',
        }).catch(() => undefined)
      }
    }
    signal.addEventListener('abort', cancelVoiceWeb, { once: true })
    const result = await runGeneration(
      async (responseId) => {
        const detail = await apiRequest<ConversationDetail>(
          '/api/conversations/messages',
          {
            method: 'POST',
            signal,
            headers: { 'X-Lea-Response-ID': responseId },
            body: JSON.stringify({
              // La voix suit la même autorisation textuelle : le backend valide la
              // formulation et peut demander confirmation avant tout réseau.
              ...buildSendMessagePayload(activeConversation, text),
              expected_profile_id: activeProfile.id,
              ...(voiceWebOperationId
                ? { web_request_id: voiceWebOperationId }
                : {}),
            }),
          },
        )
        answer =
          detail.messages.at(-1)?.role === 'assistant'
            ? detail.messages.at(-1)!.content
            : ''
        return detail
      },
      text,
      false,
    ).finally(() => signal.removeEventListener('abort', cancelVoiceWeb))
    if (result !== 'completed' || !answer) {
      throw new Error(
        'Vérifiez l’historique avant de réessayer',
      )
    }
    return { text: answer }
  }

  // Les décisions restent liées au run affiché, jamais au projet sélectionné après coup.
  const agentCheckpointControls = (
    <>
      {agentChanges?.run_id === agentRun?.run_id &&
        agentRun?.project_id === projectCatalog?.active_project_id &&
        !agentRunActive && agentChanges?.checkpoint.state === 'completed' && (
        <div className="agent-changes">
          <h3>
            {agentChanges.changes.length > 0
              ? 'Changements proposés'
              : 'Checkpoint de la tâche'}
          </h3>
          {agentChanges.changes.length > 0 ? (
            <ul>
              {agentChanges.changes.map((change) => (
                <li
                  key={`${change.change}:${change.relative_path}`}
                >
                  {change.change} — {change.relative_path}
                </li>
              ))}
            </ul>
          ) : (
            <p>Aucun fichier modifié.</p>
          )}
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
        </div>
      )}
      {agentChanges?.run_id === agentRun?.run_id && (
        agentChanges?.checkpoint.state === 'accepted' ? (
          <p className="status-ready">Changements acceptés.</p>
        ) : agentChanges?.checkpoint.state === 'rolled_back' ? (
          <p>Fichiers restaurés au checkpoint.</p>
        ) : null
      )}
    </>
  )

  return (
    <main className="app-shell">
      <div className={`app-layout${showResourceChart ? ' with-resource-chart' : ''}`}>
        <ConversationSidebar
          search={search}
          onSearch={setSearch}
          ready={
            coreStatus.state === 'ready' &&
            !settingsOpen &&
            !voiceOpen &&
            !ephemeral.active &&
            !ephemeral.busy
          }
          loading={isListLoading}
          busy={
            isAgentStarting ||
            agentRunActive ||
            isCheckpointTransition ||
            isGenerating ||
            isRenaming ||
            isConversationLoading ||
            settingsOpen ||
            voiceOpen ||
            ephemeral.active ||
            ephemeral.busy
          }
          conversations={conversations}
          programmingReady={programmingReady}
          activeId={ephemeral.active ? undefined : activeConversation?.id}
          onSelect={(id) => void loadConversation(id)}
          onRename={openRename}
          onDelete={(conversation) => void handleDelete(conversation)}
          onNew={handleNewConversation}
          onSettings={toggleSettings}
          settingsRef={settingsButton}
          coreControls={
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
                Démarrer
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
                Arrêter
              </button>
            </div>
          }
        />
        <div className="main-pane">
          {(settingsOpen || voiceOpen) && (
            <div className="core-status-banner">
              {coreNotice}
              <div ref={setAlternateNoticeHost} />
            </div>
          )}
          {settingsOpen && (
            <Settings
              ref={settingsPanel}
              onBack={closeSettings}
              onSaved={setPreferences}
              theme={theme}
              onTheme={chooseTheme}
              themeError={themeError}
            />
          )}
          <section
            className="chat"
            aria-label="Conversation avec Léa"
            hidden={settingsOpen || voiceOpen}
          >
            <header className="chat-topbar has-core-notice">
              <button
                type="button"
                className="icon-button ephemeral-toggle"
                aria-label={
                  ephemeral.active
                    ? 'Quitter le chat éphémère'
                    : 'Chat éphémère'
                }
                title={
                  ephemeral.active
                    ? 'Quitter le chat éphémère'
                    : 'Chat éphémère'
                }
                aria-pressed={ephemeral.active}
                disabled={
                  normalGenerating ||
                  ephemeral.busy ||
                  isConversationLoading ||
                  isRenaming ||
                  isModelTransition ||
                  isCoreTransition ||
                  (!ephemeral.active &&
                    (selectedProfileId !== 'general' ||
                      coreStatus.state !== 'ready'))
                }
                onClick={async () => {
                  // Le mode normal conserve son brouillon ; aucun texte éphémère ne lui est transféré.
                  const entering = !ephemeral.active
                  if (entering) normalDraft.current = question
                  if (await ephemeral.toggle()) {
                    closeEditors()
                    setQuestion(entering ? '' : normalDraft.current)
                    focusQuestion()
                  }
                }}
              >
                <Icon name="ephemeral" />
              </button>
              <div className="topbar-notices">
                {!settingsOpen && !voiceOpen && coreNotice}
                <div ref={setResourceNoticeHost} />
              </div>
              {modelCatalog && (
                <div className="model-selector">
                  <label htmlFor="model-profile">Profil de Léa</label>
                  <select
                    id="model-profile"
                    value={selectedProfileId}
                    onChange={(event) =>
                      void handleModelChange(event.target.value)
                    }
                    disabled={modelChangeBlocked}
                  >
                    {modelCatalog.profiles
                      .filter((profile) => profile.enabled)
                      .sort(
                        (left, right) =>
                          left.display_order - right.display_order,
                      )
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
                    {shortNotice(modelPresentation.message, 'model')}
                  </p>
                  {modelError && (
                    <p
                      className="model-profile-status status-error"
                      role="alert"
                    >
                      {shortNotice(modelError, 'model')}
                    </p>
                  )}
                </div>
              )}
            </header>
            {!modelCatalog && coreStatus.state === 'ready' && modelError && (
              <p className="runtime-error status-error" role="alert">
                {shortNotice(modelError, 'model')}
              </p>
            )}

            {projectCapabilityActive && (
              <div className="project-dock">
                <section className="project-controls" aria-label="Projet de programmation actif">
                  <h2>Projet</h2>
                  {projectCatalog && projectCatalog.projects.length > 0 ? (
                    <>
                      <label className="sr-only" htmlFor="active-project">Projet actif dans IA_WORKSPACE</label>
                      <select
                        id="active-project"
                        value={projectCatalog.active_project_id ?? ''}
                        onChange={(event) => void selectProject(event.target.value)}
                        disabled={isProjectTransition || isGenerating || isModelTransition ||
                          agentRunActive || isAgentStarting || isCheckpointTransition}
                      >
                        <option value="">Sélectionner un projet</option>
                        {projectCatalog.projects.map((project) => (
                          <option key={project.id} value={project.id}>{project.name}</option>
                        ))}
                      </select>
                    </>
                  ) : (
                    <p className="conversation-empty">Aucun projet dans IA_WORKSPACE.</p>
                  )}
                  <button
                    type="button"
                    className="secondary-button compact-button"
                    onClick={() => void refreshProjects()}
                    disabled={isProjectTransition || isGenerating || agentRunActive || isAgentStarting || isCheckpointTransition}
                  >
                    {isProjectTransition ? 'Actualisation…' : 'Actualiser'}
                  </button>
                  {projectError && <p className="chat-error" role="alert">{shortNotice(projectError, 'project')}</p>}
                </section>
              </div>
            )}

            <div
              className={`chat-scroll${!displayedConversation?.messages.length && !displayedPending && !(programmingActive && agentRun) ? ' chat-empty' : ''}`}
              ref={chatScroll}
              onScroll={() => {
                const panel = chatScroll.current
                if (panel)
                  followMessages.current =
                    panel.scrollHeight - panel.scrollTop - panel.clientHeight <
                    80
              }}
            >
              <div className="chat-content">
                {programmingActive &&
                  (Boolean(agentPollingError) ||
                    agentPollingTone !== 'normal' ||
                    Boolean(agentError)) && (
                    <section
                      className="agent-controls"
                      aria-label="Tâche OpenHands"
                    >
                      <h2 className="sr-only">Tâche OpenHands</h2>
                      {agentPollingError && (
                        <p className="agent-run-notice status-error" role="alert">
                          {shortNotice(agentPollingError, 'task')}
                        </p>
                      )}
                      {agentPollingTone !== 'normal' && (
                        <p
                          className={`agent-run-notice status-${agentPollingTone}`}
                          role={
                            agentPollingTone === 'error' ? 'alert' : undefined
                          }
                        >
                          {shortNotice(agentPollingHealth.message, 'task')}
                        </p>
                      )}
                      {agentError && (
                        <p className="chat-error" role="alert">
                          {shortNotice(agentError, 'task')}
                        </p>
                      )}
                    </section>
                  )}

                <section
                  className="conversation"
                  aria-label="Conversation"
                  aria-busy={isGenerating || isConversationLoading}
                >
                  {!ephemeral.active &&
                    renameTarget &&
                    renameDraft !== null && (
                      <form
                        className="inline-editor rename-editor"
                        onSubmit={(event) => void handleRenameSubmit(event)}
                      >
                        <label htmlFor="conversation-title">
                          Nouveau titre
                        </label>
                        <input
                          id="conversation-title"
                          value={renameDraft}
                          onChange={(event) =>
                            setRenameDraft(event.target.value)
                          }
                          maxLength={100}
                          autoFocus
                          disabled={isRenaming || isGenerating}
                        />
                        <div className="editor-actions">
                          <button
                            type="submit"
                            className="compact-button"
                            disabled={
                              isRenaming ||
                              isGenerating ||
                              coreStatus.state !== 'ready'
                            }
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

                  {!displayedConversation?.messages.length &&
                    !displayedPending &&
                    !settingsOpen &&
                    !voiceOpen &&
                    !(programmingActive && agentRun) && (
                      <Welcome
                        ephemeral={ephemeral.active}
                        index={welcomeIndex}
                        profileId={activeProfile?.id}
                      />
                    )}
                  {isConversationLoading && (
                    <p className="conversation-pending">Chargement…</p>
                  )}
                  <div className="conversation-list" aria-live="polite">
                    {/* Les anciens runs sans conversation restent lisibles sans réécrire l'historique. */}
                    {programmingActive && agentRun && !agentRun.conversation_id && (
                      <>
                        <article className="message message-user">
                          <strong>Vous</strong>
                          <MarkdownMessage content={agentRun.task} />
                        </article>
                        <AgentRunResult run={agentRun}>{agentCheckpointControls}</AgentRunResult>
                      </>
                    )}
                    {displayedConversation?.messages.map((message) => (
                      programmingActive && message.role === 'assistant' &&
                      agentRun && message.agent_run_id === agentRun.run_id ? (
                        <AgentRunResult key={message.id} run={agentRun}>
                          {agentCheckpointControls}
                        </AgentRunResult>
                      ) :
                      <article
                        className={`message message-${message.role} message-${message.status}`}
                        key={message.id}
                      >
                        <strong>
                          {message.role === 'user' ? 'Vous' : 'Léa'}
                        </strong>
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
                            onSubmit={(event) =>
                              void handleEditSubmit(event, message)
                            }
                          >
                            <label htmlFor={`message-edit-${message.id}`}>
                              Modifier votre message
                            </label>
                            <textarea
                              id={`message-edit-${message.id}`}
                              value={editDraft}
                              onChange={(event) =>
                                setEditDraft(event.target.value)
                              }
                              rows={4}
                              autoFocus
                              disabled={isGenerating}
                            />
                            <div className="editor-actions">
                              <button
                                type="submit"
                                className="compact-button"
                                disabled={
                                  isGenerating || coreStatus.state !== 'ready'
                                }
                              >
                                {isGenerating
                                  ? 'Envoi…'
                                  : 'Enregistrer et régénérer'}
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
                          <MarkdownMessage content={message.content} />
                        )}
                        {message.role === 'assistant' && (
                          <WebSources sources={message.web_sources} />
                        )}
                        {message.status === 'failed' && (
                          <p className="message-error">
                            {shortNotice(messageFailureLabel(message), 'conversation')}
                          </p>
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
                            {!ephemeral.active &&
                              message.role === 'user' &&
                              !isWebFailure(message) &&
                              allowsDestructiveMessageAction(message) && (
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() => handleEdit(message)}
                                  disabled={
                                    isGenerating ||
                                    isConversationLoading ||
                                    isRenaming
                                  }
                                >
                                  Modifier
                                </button>
                              )}
                            {!ephemeral.active &&
                              message.role === 'user' &&
                              message.status === 'failed' &&
                              !isWebFailure(message) &&
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
                            {!ephemeral.active &&
                              message.role === 'user' &&
                              message.status === 'failed' &&
                              isWebFailure(message) &&
                              allowsDestructiveMessageAction(message) && (
                                <button
                                  type="button"
                                  className="text-button"
                                  onClick={() => prepareWebRetry(message)}
                                  disabled={
                                    isGenerating ||
                                    isConversationLoading ||
                                    isRenaming ||
                                    preferences?.web_enabled !== true ||
                                    coreStatus.state !== 'ready'
                                  }
                                >
                                  Préparer une nouvelle recherche
                                </button>
                              )}
                          </div>
                        )}
                      </article>
                    ))}
                    {displayedPending && (
                      <article className="message message-user message-pending">
                        <strong>Vous</strong>
                        <MarkdownMessage content={displayedPending} />
                      </article>
                    )}
                  </div>
                  {isGenerating && (
                    <p className="conversation-pending">Léa répond…</p>
                  )}
                  {copyFeedback && (
                    <p className="copy-feedback" aria-live="polite">
                      {copyFeedback}
                    </p>
                  )}
                  {(ephemeral.error ||
                    (!ephemeral.active && conversationError)) && (
                    <p className="chat-error" role="alert">
                      {shortNotice(ephemeral.error || conversationError, 'conversation')}
                    </p>
                  )}
                </section>
              </div>
            </div>
            <div className="composer-container">
              <form
                className="composer"
                aria-label={
                  programmingActive ? 'Tâche de programmation' : 'Votre question'
                }
                onSubmit={handleSubmit}
              >
                <label className="sr-only" htmlFor="question">
                  {programmingActive ? 'Tâche de programmation' : 'Votre question'}
                </label>
                {/* Réservé à l'import de fichiers dans une étape future ; aucune action pour le moment. */}
                <button
                  type="button"
                  className="icon-button composer-add"
                  aria-label="Ajouter des fichiers (indisponible)"
                  title="Import de fichiers indisponible"
                  disabled
                >
                  <Icon name="plus" />
                </button>
                <AutoTextarea
                  ref={questionInput}
                  id="question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={handleQuestionKeyDown}
                  placeholder={
                    programmingActive
                      ? 'Décris la correction ou l’évolution à réaliser…'
                      : 'Écrivez votre question…'
                  }
                  rows={1}
                  autoComplete="off"
                  disabled={
                    isGenerating ||
                    ephemeral.busy ||
                    isConversationLoading ||
                    isRenaming ||
                    (programmingActive &&
                      (isAgentStarting || isAgentCancelling || agentRunActive))
                  }
                />
                {!ephemeral.active &&
                  !programmingActive &&
                  preferences?.web_enabled !== true && (
                  <p className="web-note">
                    Web désactivé dans les paramètres
                  </p>
                )}
                {webInProgress && (
                  <div className="web-progress" role="status">
                    <span>Recherche Web autorisée en cours…</span>
                  </div>
                )}
                <div className="composer-voice" ref={setVoiceControlsHost} />
              </form>
            </div>
            <div className="chat-footer">
              <p className="composer-hint">
                {ephemeral.active
                  ? 'Sans historique local · Traces possibles sur les sites consultés'
                  : 'Vérifiez les réponses de Léa'}
              </p>
            </div>
          </section>
          <VoiceControls
            composerSendButton={
              isGenerating || isAgentStarting || agentRunActive || isAgentCancelling ? (
                <button
                  type="button"
                  className="icon-button send-button"
                  aria-label="Arrêter la réponse"
                  title="Arrêter la réponse"
                  aria-busy={isResponseStopping || isAgentCancelling}
                  disabled={isResponseStopping || isAgentCancelling}
                  onClick={() => void stopResponse()}
                >
                  <Icon name="stop" />
                </button>
              ) : showSendAction ? (
                <button
                  ref={sendButton}
                  className="icon-button send-button"
                  aria-label="Envoyer"
                  title="Envoyer"
                  type="submit"
                  disabled={
                    isGenerating ||
                    ephemeral.busy ||
                    isConversationLoading ||
                    isRenaming ||
                    coreStatus.state !== 'ready' ||
                    (programmingActive &&
                      (isAgentStarting ||
                        isAgentCancelling ||
                        isCheckpointTransition ||
                        agentRunActive ||
                        !projectCatalog?.active_project_id))
                  }
                >
                  <Icon name="send" />
                </button>
              ) : null
            }
            ephemeral={ephemeral.active}
            controlsHost={voiceControlsHost}
            preferences={preferences}
            onMode={setVoiceOpen}
            onDictated={dictated}
            onSend={sendVoice}
            onStopResponse={stopResponse}
            stopping={isResponseStopping || isAgentCancelling}
            hidden={settingsOpen}
            contextKey={`${coreStatus.state}:${selectedProfileId}:${projectCatalog?.active_project_id ?? ''}:${ephemeral.conversation?.id ?? 'normal'}`}
            ready={coreStatus.state === 'ready' && Boolean(activeProfile)}
            blocked={
              isGenerating ||
              ephemeral.busy ||
              isAgentStarting ||
              agentRunActive ||
              isCheckpointTransition ||
              isModelTransition ||
              isCoreTransition ||
              isProjectTransition ||
              isConversationLoading ||
              isRenaming
            }
          />
          <ResourcePanel
            noticeHost={settingsOpen || voiceOpen ? alternateNoticeHost : resourceNoticeHost}
            enabled={
              coreStatus.state !== 'stopped' &&
              coreStatus.state !== 'stopping' &&
              Boolean(activeProfile || loadingProfile)
            }
            profileId={(loadingProfile ?? activeProfile)?.id}
            showChart={showResourceChart}
          />
        </div>
      </div>
      {preferencesError && <p role="status">{shortNotice(preferencesError, 'preferences')}</p>}
    </main>
  )
}

export default App

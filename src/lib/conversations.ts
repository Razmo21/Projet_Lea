export const backendOrigin = 'http://127.0.0.1:8000'

const AMBIGUOUS_WEB_REQUEST = /\b(?:peux[ -]tu|pourrais[ -]tu|tu peux)\b.{0,80}\b(?:chercher|regarder|v[ée]rifier|consulter|trouver|ouvrir)\b/is
const WEB_CONFIRMATION = /^\s*(?:oui(?:\s*,?\s*(?:vas[ -]y|cherche|recherche|d'accord|ok))?|vas[ -]y|d'accord|ok|(?:toi\s*,?\s*)?(?:cherche|recherche)(?:\s+(?:s['’]il\s+te\s+pla[îi]t|stp))?)\s*[.!]?\s*$/i

export type MessageStatus = 'pending' | 'completed' | 'failed'
export type MessageKind = 'conversation' | 'memory'

export type WebSource = {
  source_id: string
  title: string
  url: string
  domain: string
  snippet: string
  provider: string
  consulted_at: string
  published_at: string | null
  updated_at: string | null
  document_date: string | null
  retrieval_status: 'read' | 'snippet_only'
  source_kind: 'html' | 'dynamic_html' | 'search_snippet' | 'pdf' | 'video_metadata' | 'video_transcript'
  limitations: string | null
}

// Présente la nature réellement extraite sans laisser croire qu'une vidéo a été visionnée.
export function webSourceKindLabel(source: WebSource): string {
  switch (source.source_kind) {
    case 'dynamic_html':
      return 'page JavaScript lue'
    case 'pdf':
      return 'PDF lu'
    case 'video_transcript':
      return 'transcription publique'
    case 'video_metadata':
      return 'métadonnées vidéo seulement'
    case 'search_snippet':
      return 'extrait du moteur seulement'
    default:
      return 'page HTML lue'
  }
}

export type ConversationMessage = {
  id: string
  conversation_id: string
  position: number
  role: 'user' | 'assistant'
  content: string
  status: MessageStatus
  kind: MessageKind
  agent_run_id?: string | null
  model_id: string | null
  profile_id: string | null
  web_sources: WebSource[]
  error: string | null
  failure_kind?: string | null
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
  has_agent_runs?: boolean
}

export type ConversationDetail = ConversationSummary & {
  messages: ConversationMessage[]
  web_confirmation_pending?: boolean
}

// Réserve les actions destructives aux tours de conversation ordinaires.
export function allowsDestructiveMessageAction(
  message: Pick<ConversationMessage, 'kind' | 'agent_run_id'>,
): boolean {
  return message.kind === 'conversation' && !message.agent_run_id
}

// Distingue la collecte Web de l'inférence, y compris après un rechargement.
export function messageFailureLabel(
  message: Pick<ConversationMessage, 'error' | 'failure_kind'>,
): string {
  switch (message.failure_kind) {
    case 'web_blocked':
      return 'Fournisseur Web bloqué.'
    case 'web_timeout':
      return 'Recherche Web trop lente.'
    case 'web_no_results':
      return 'Aucun résultat Web exploitable.'
    case 'web_cancelled':
      return 'Recherche Web annulée.'
    case 'web_policy':
    case 'web_authorization':
      return 'Recherche Web refusée.'
    case 'web_network':
      return 'Recherche Web impossible.'
    case 'web_http':
    case 'web_unavailable':
    case 'web_providers_unavailable':
      return 'Recherche Web indisponible.'
    case 'web_error':
      return 'Recherche ou synthèse Web échouée.'
    case 'web_extraction':
      return 'Contenu Web inaccessible.'
    default:
      return message.error === 'interrupted'
        ? 'Génération interrompue.'
        : 'Échec de la génération.'
  }
}

// Un échec de collecte exige un nouvel accord du tour, jamais un retry implicite.
export function isWebFailure(
  message: Pick<ConversationMessage, 'failure_kind'>,
): boolean {
  return message.failure_kind?.startsWith('web_') === true
}

// Le navigateur n'envoie jamais l'historique : SQLite et le backend restent autoritaires.
export type SendMessagePayload = {
  conversation_id: string | null
  message: string
  expected_revision: number | null
  web_request_id?: string
}

// Produit un petit séquenceur qui ignore les réponses réseau devenues obsolètes.
export function createLatestRequestGate() {
  // Un ticket invalide les réponses arrivées après une navigation plus récente.
  let latestRequest = 0

  return {
    // Ouvre une nouvelle génération de requête et retourne son ticket.
    begin(): number {
      latestRequest += 1
      return latestRequest
    },
    // Rend immédiatement caducs tous les tickets déjà distribués.
    invalidate(): void {
      latestRequest += 1
    },
    // Expose le ticket courant pour les contrôles synchrones.
    current(): number {
      return latestRequest
    },
    // Vérifie qu'une réponse appartient encore à la navigation active.
    isCurrent(request: number): boolean {
      return request === latestRequest
    },
  }
}

// Construit le seul payload autorisé sans recopier l'historique côté navigateur.
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

// Aligne l'accord ponctuel de l'interface sur le classifieur backend.
export function isExplicitWebRequest(message: string): boolean {
  const directUrl = /https?:\/\//i.test(message)
  const web = /\b(?:web|internet|en ligne|site|sources?)\b/i.test(message)
  const action = /\b(?:cherche|recherche|consulte|v[ée]rifie|ouvre|regarde|trouve)\w*\b/i.test(message)
  return directUrl || (web && action)
}

// Prédit une collecte pour afficher son suivi ; le backend reste seul arbitre de l'accord.
export function webAuthorizationForTurn(message: string): boolean {
  return isExplicitWebRequest(message)
}

// Une formulation ambiguë reste conversationnelle afin que le backend demande confirmation.
export function isAmbiguousWebRequest(message: string): boolean {
  return AMBIGUOUS_WEB_REQUEST.test(message)
}

// Sert uniquement au suivi visuel ; le backend consomme et valide la vraie confirmation.
export function isWebConfirmation(message: string): boolean {
  return WEB_CONFIRMATION.test(message)
}

// Prépare une nouvelle demande visible après un échec, y compris si le tour était une confirmation.
export function webRetryDraft(
  failed: Pick<ConversationMessage, 'content' | 'position'>,
  messages: Pick<ConversationMessage, 'content' | 'position' | 'role'>[],
): string {
  const question = isWebConfirmation(failed.content)
    ? messages.find((message) => message.role === 'user' && message.position === failed.position - 2)?.content
    : failed.content
  if (!question) return ''
  return isExplicitWebRequest(question) ? question : `Cherche sur Internet : ${question}`
}

// Extrait uniquement un UUID canonique de la barre d'adresse.
export function conversationIdFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get('conversation')
  return value && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : null
}

// Synchronise l'URL sans stocker de contenu de conversation dans le navigateur.
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

// Formate un horodatage valide dans la locale de l'utilisateur.
export function formatActivity(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat('fr-CA', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(date)
}

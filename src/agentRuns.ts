export type AgentRunState =
  | 'pending'
  | 'running'
  | 'waiting_for_tool'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'limit_reached'

export type AgentRunValidationStatus = 'pending' | 'validated' | 'unverified' | 'not_requested' | 'failed'

export type AgentRun = {
  run_id: string
  conversation_id: string | null
  project_id: string
  profile_id: string
  openhands_session_id: string | null
  task: string
  state: AgentRunState
  started_at: string | null
  finished_at: string | null
  result_summary: string | null
  checkpoint_id: string | null
  created_at: string
  updated_at: string
  validation_status?: AgentRunValidationStatus
}

export type Checkpoint = {
  checkpoint_id: string
  run_id: string
  project_id: string
  project_relative_path: string
  project_identity: string
  state: 'ready' | 'completed' | 'accepted' | 'rolled_back' | 'conflict' | 'failed'
  created_at: string
  completed_at: string | null
  accepted_at: string | null
  rolled_back_at: string | null
  conflict_at: string | null
  error: string | null
}

export type AgentRunChange = {
  relative_path: string
  entry_type: 'file' | 'directory'
  change: 'created' | 'modified' | 'deleted'
}

export type AgentRunChanges = {
  run_id: string
  checkpoint: Checkpoint
  changes: AgentRunChange[]
}

export type PollingHealth = {
  consecutive_failures: number
  message: string | null
}

export type PollingTone = 'normal' | 'warning' | 'error'

export type RuntimeStatusPresentation = {
  tone: 'normal' | 'ready' | 'warning' | 'error'
  message: string
}

export type AgentRunValidationPresentation = {
  tone: 'normal' | 'ready' | 'warning' | 'error'
  message: string
  accepts_changes: boolean
}

const agentRunStates = new Set<AgentRunState>([
  'pending', 'running', 'waiting_for_tool', 'completed', 'failed', 'cancelled', 'limit_reached',
])

const checkpointStates = new Set<Checkpoint['state']>([
  'ready', 'completed', 'accepted', 'rolled_back', 'conflict', 'failed',
])

const agentRunValidationStates = new Set<AgentRunValidationStatus>([
  'pending', 'validated', 'unverified', 'not_requested', 'failed',
])

// Vérifie une ligne API durable avant de l'afficher comme état agentique.
export function isAgentRun(value: unknown): value is AgentRun {
  if (typeof value !== 'object' || value === null) return false
  const run = value as Record<string, unknown>
  return (
    typeof run.run_id === 'string' &&
    (run.conversation_id === null || typeof run.conversation_id === 'string') &&
    typeof run.project_id === 'string' &&
    typeof run.profile_id === 'string' &&
    (run.openhands_session_id === null || typeof run.openhands_session_id === 'string') &&
    typeof run.task === 'string' &&
    typeof run.state === 'string' && agentRunStates.has(run.state as AgentRunState) &&
    (run.started_at === null || typeof run.started_at === 'string') &&
    (run.finished_at === null || typeof run.finished_at === 'string') &&
    (run.result_summary === null || typeof run.result_summary === 'string') &&
    (run.checkpoint_id === null || typeof run.checkpoint_id === 'string') &&
    typeof run.created_at === 'string' &&
    typeof run.updated_at === 'string' &&
    (
      run.validation_status === undefined ||
      (typeof run.validation_status === 'string' &&
        agentRunValidationStates.has(run.validation_status as AgentRunValidationStatus))
    )
  )
}

// Refuse un catalogue partiel plutôt que d'inventer l'état du dernier run.
export function isAgentRunList(value: unknown): value is { runs: AgentRun[] } {
  if (typeof value !== 'object' || value === null) return false
  const payload = value as Record<string, unknown>
  return Array.isArray(payload.runs) && payload.runs.every(isAgentRun)
}

// Contrôle le diff minimal sans laisser un chemin absolu atteindre l'interface.
export function isAgentRunChanges(value: unknown): value is AgentRunChanges {
  if (typeof value !== 'object' || value === null) return false
  const payload = value as Record<string, unknown>
  if (
    typeof payload.run_id !== 'string' ||
    typeof payload.checkpoint !== 'object' || payload.checkpoint === null ||
    !Array.isArray(payload.changes)
  ) return false
  const checkpoint = payload.checkpoint as Record<string, unknown>
  const validCheckpoint =
    typeof checkpoint.checkpoint_id === 'string' &&
    typeof checkpoint.run_id === 'string' &&
    typeof checkpoint.project_id === 'string' &&
    typeof checkpoint.project_relative_path === 'string' &&
    !/^(?:[a-z]:|[\\/])/i.test(checkpoint.project_relative_path) &&
    typeof checkpoint.project_identity === 'string' &&
    typeof checkpoint.state === 'string' && checkpointStates.has(checkpoint.state as Checkpoint['state'])
  return validCheckpoint && payload.changes.every((change) => {
    if (typeof change !== 'object' || change === null) return false
    const item = change as Record<string, unknown>
    return (
      typeof item.relative_path === 'string' &&
      !/^(?:[a-z]:|[\\/])|\.\./i.test(item.relative_path) &&
      (item.entry_type === 'file' || item.entry_type === 'directory') &&
      (item.change === 'created' || item.change === 'modified' || item.change === 'deleted')
    )
  })
}

// Distingue les états qui peuvent encore déclencher des outils OpenHands réels.
export function isActiveAgentRun(run: AgentRun | null): boolean {
  return Boolean(run && !['completed', 'failed', 'cancelled', 'limit_reached'].includes(run.state))
}

// Transforme un payload de polling invalide en erreur explicite plutôt que de le taire.
export function requireAgentRun(value: unknown): AgentRun {
  if (!isAgentRun(value)) {
    throw new Error('Le statut du run OpenHands est invalide.')
  }
  return value
}

// Réinitialise le suivi local après une réponse de polling structurellement valide.
export function resetPollingHealth(): PollingHealth {
  return { consecutive_failures: 0, message: null }
}

// Mémorise les échecs consécutifs sans faire clignoter une erreur dès le premier raté réseau.
export function recordPollingFailure(current: PollingHealth, message: string): PollingHealth {
  const normalized = message.trim() || 'La vérification locale est indisponible.'
  return {
    consecutive_failures: Math.min(current.consecutive_failures + 1, 3),
    message: normalized,
  }
}

// Distingue un incident isolé, un avertissement durable et une panne de polling persistante.
export function pollingTone(health: PollingHealth): PollingTone {
  if (health.consecutive_failures >= 3) return 'error'
  if (health.consecutive_failures >= 2) return 'warning'
  return 'normal'
}

// Produit un rendu du runtime dont un état ready confirmé reste toujours distinct d'une erreur passée.
export function runtimeStatusPresentation(
  profileName: string | null,
  runtimeState: 'ready' | 'loading' | 'error' | null,
  runtimeMessage: string | null,
  health: PollingHealth,
): RuntimeStatusPresentation {
  if (runtimeState === 'error') {
    return { tone: 'error', message: runtimeMessage || 'Le runtime du profil a signalé une erreur.' }
  }
  const healthTone = pollingTone(health)
  if (healthTone !== 'normal') {
    return {
      tone: healthTone,
      message: health.message || 'La vérification du runtime est indisponible.',
    }
  }
  if (runtimeState === 'loading') {
    return { tone: 'warning', message: runtimeMessage || 'Chargement du profil…' }
  }
  if (runtimeState === 'ready' && profileName) {
    return { tone: 'ready', message: `${profileName} est prêt.` }
  }
  return { tone: 'normal', message: 'État du profil indisponible.' }
}

// Ne montre que le dernier run du projet réellement sélectionné, jamais celui d'un projet précédent.
export function latestAgentRunForProject(runs: AgentRun[], projectId: string | null): AgentRun | null {
  if (!projectId) return null
  return runs.find((run) => run.project_id === projectId) ?? null
}

// Traite les anciens enregistrements sans champ de validation comme non vérifiés, jamais comme réussis.
export function effectiveValidationStatus(run: AgentRun): AgentRunValidationStatus {
  if (run.validation_status) return run.validation_status
  return run.state === 'completed' ? 'unverified' : 'pending'
}

// Rend la validation explicite afin que la fin technique d'un run ne soit pas confondue avec son succès.
export function agentRunValidationPresentation(run: AgentRun): AgentRunValidationPresentation {
  switch (effectiveValidationStatus(run)) {
    case 'validated':
      return { tone: 'ready', message: 'Validation réelle confirmée.', accepts_changes: true }
    case 'unverified':
      return {
        tone: 'warning',
        message: 'Run terminé sans validation réelle : les changements ne peuvent pas être acceptés.',
        accepts_changes: false,
      }
    case 'failed':
      return { tone: 'error', message: 'La validation du run a échoué.', accepts_changes: false }
    case 'not_requested':
      return { tone: 'normal', message: 'Aucune validation n’était demandée.', accepts_changes: false }
    default:
      return { tone: 'warning', message: 'Validation du run en attente.', accepts_changes: false }
  }
}

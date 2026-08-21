export type PublicModelProfile = {
  id: string
  display_name: string
  model_type: string
  role: string
  enabled: boolean
  display_order: number
  context_tokens: number
  capabilities: string[]
}

export type ModelCatalog = {
  default_profile_id: string
  active_profile_id: string
  profiles: PublicModelProfile[]
}

export type ModelRuntimeStatus = {
  state: 'ready' | 'loading' | 'error'
  message: string
  active_profile_id: string
  loading_profile_id: string | null
  generation_active: boolean
  agent_run_active: boolean
}

// Valide la forme publique minimale avant que l'interface n'utilise le registre.
export function isModelCatalog(value: unknown): value is ModelCatalog {
  if (typeof value !== 'object' || value === null) return false
  const catalog = value as Record<string, unknown>
  if (
    typeof catalog.default_profile_id !== 'string' ||
    typeof catalog.active_profile_id !== 'string' ||
    !Array.isArray(catalog.profiles)
  ) return false

  return catalog.profiles.every((item) => {
    if (typeof item !== 'object' || item === null) return false
    const profile = item as Record<string, unknown>
    return (
      typeof profile.id === 'string' &&
      typeof profile.display_name === 'string' &&
      typeof profile.model_type === 'string' &&
      typeof profile.role === 'string' &&
      typeof profile.enabled === 'boolean' &&
      typeof profile.display_order === 'number' &&
      typeof profile.context_tokens === 'number' &&
      Array.isArray(profile.capabilities) &&
      profile.capabilities.every((capability) => typeof capability === 'string')
    )
  })
}

// Retrouve le profil actif sans inventer de valeur de secours côté navigateur.
export function activeModelProfile(catalog: ModelCatalog): PublicModelProfile | null {
  return catalog.profiles.find((profile) => profile.id === catalog.active_profile_id) ?? null
}

// Refuse un statut partiel pour que le sélecteur n'invente jamais l'état du runtime.
export function isModelRuntimeStatus(value: unknown): value is ModelRuntimeStatus {
  if (typeof value !== 'object' || value === null) return false
  const status = value as Record<string, unknown>
  return (
    (status.state === 'ready' || status.state === 'loading' || status.state === 'error') &&
    typeof status.message === 'string' &&
    typeof status.active_profile_id === 'string' &&
    (status.loading_profile_id === null || typeof status.loading_profile_id === 'string') &&
    typeof status.generation_active === 'boolean' &&
    typeof status.agent_run_active === 'boolean'
  )
}

// Une activation est possible seulement vers une autre cible, hors activité modèle.
export function canActivateModel(
  status: ModelRuntimeStatus | null,
  targetProfileId: string,
): boolean {
  return Boolean(
    status &&
    status.state === 'ready' &&
    !status.loading_profile_id &&
    !status.generation_active &&
    !status.agent_run_active &&
    targetProfileId !== status.active_profile_id,
  )
}

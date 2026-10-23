export type ReasoningLevel = 'low' | 'high'

export type Preferences = {
  revision: number
  general_reasoning: ReasoningLevel
  general_reasoning_available: boolean
  veterinary_reasoning: ReasoningLevel
  veterinary_reasoning_available: boolean
  profile_settings: ProfileSetting[]
  show_resource_chart: boolean
} & VoicePreferences

export type ProfileSetting = {
  id: string
  display_name: string
  model_name: string
  reasoning_available: boolean
}

export type VoicePreferences = {
  voice_microphone_id: string
  voice_language: 'fr' | 'en'
  voice_enabled: boolean
  voice_id: string
  voice_volume: number
  voice_rate: number
}

export const defaultVoicePreferences: VoicePreferences = {
  voice_microphone_id: '', voice_language: 'fr', voice_enabled: true,
  voice_id: 'lea_voice', voice_volume: 1, voice_rate: 1,
}

export type PreferenceChange = {
  expected_revision: number
  general_reasoning?: ReasoningLevel
  veterinary_reasoning?: ReasoningLevel
  show_resource_chart?: boolean
} & Partial<VoicePreferences>

// Une réponse HTTP réussie ne suffit pas : la valeur persistée doit être exploitable.
export function isPreferences(value: unknown): value is Preferences {
  if (typeof value !== 'object' || value === null) return false
  const data = value as Record<string, unknown>
  return Number.isSafeInteger(data.revision) && Number(data.revision) >= 0 &&
    typeof data.general_reasoning_available === 'boolean' &&
    typeof data.veterinary_reasoning_available === 'boolean' &&
    Array.isArray(data.profile_settings) && data.profile_settings.every((profile) => {
      if (typeof profile !== 'object' || profile === null) return false
      const item = profile as Record<string, unknown>
      return typeof item.id === 'string' && typeof item.display_name === 'string' &&
        typeof item.model_name === 'string' && typeof item.reasoning_available === 'boolean'
    }) &&
    typeof data.show_resource_chart === 'boolean' &&
    typeof data.voice_microphone_id === 'string' && data.voice_microphone_id.length <= 256 &&
    (data.voice_language === 'fr' || data.voice_language === 'en') &&
    typeof data.voice_enabled === 'boolean' && typeof data.voice_id === 'string' && /^[a-zA-Z0-9_-]+$/.test(data.voice_id) &&
    typeof data.voice_volume === 'number' && data.voice_volume >= 0 && data.voice_volume <= 1 &&
    typeof data.voice_rate === 'number' && data.voice_rate >= 0.75 && data.voice_rate <= 1.5 &&
    (data.general_reasoning === 'low' || data.general_reasoning === 'high') &&
    (data.veterinary_reasoning === 'low' || data.veterinary_reasoning === 'high')
}

// Ce chemin relatif reste servi par Vite même lorsque FastAPI et les modèles sont arrêtés.
export async function requestPreferences(
  change?: PreferenceChange,
  transport: typeof fetch = fetch,
): Promise<Preferences> {
  let response: Response
  try {
    response = await transport('/api/preferences', {
      method: change ? 'POST' : 'GET',
      cache: 'no-store',
      signal: AbortSignal.timeout(20_000),
      headers: change ? { 'Content-Type': 'application/json' } : undefined,
      body: change ? JSON.stringify(change) : undefined,
    })
  } catch {
    throw new Error('Le contrôleur local est indisponible. Rechargez pour vérifier les paramètres enregistrés.')
  }
  let data: unknown
  try {
    data = await response.json()
  } catch {
    throw new Error('Le contrôleur local n’a pas confirmé les paramètres. Rechargez pour vérifier leur état.')
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail
    throw new Error(typeof detail === 'string' ? detail : 'Les paramètres n’ont pas pu être confirmés.')
  }
  if (!isPreferences(data)) throw new Error('Les paramètres reçus sont invalides.')
  if (change && (
    data.revision !== change.expected_revision + 1 ||
    (change.general_reasoning !== undefined && (!data.general_reasoning_available || data.general_reasoning !== change.general_reasoning)) ||
    (change.veterinary_reasoning !== undefined && (!data.veterinary_reasoning_available || data.veterinary_reasoning !== change.veterinary_reasoning)) ||
    (change.show_resource_chart !== undefined && data.show_resource_chart !== change.show_resource_chart) ||
    Object.keys(defaultVoicePreferences).some((key) => {
      const field = key as keyof VoicePreferences
      return change[field] !== undefined && data[field] !== change[field]
    })
  )) {
    throw new Error('La confirmation ne correspond pas au choix envoyé. Rechargez les paramètres.')
  }
  return data
}

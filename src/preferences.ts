export type ReasoningLevel = 'low' | 'high'

export type Preferences = {
  revision: number
  general_reasoning: ReasoningLevel
  general_reasoning_available: boolean
  show_resource_chart: boolean
}

export type PreferenceChange = {
  expected_revision: number
  general_reasoning?: ReasoningLevel
  show_resource_chart?: boolean
}

// Une réponse HTTP réussie ne suffit pas : la valeur persistée doit être exploitable.
export function isPreferences(value: unknown): value is Preferences {
  if (typeof value !== 'object' || value === null) return false
  const data = value as Record<string, unknown>
  return Number.isSafeInteger(data.revision) && Number(data.revision) >= 0 &&
    typeof data.general_reasoning_available === 'boolean' &&
    typeof data.show_resource_chart === 'boolean' &&
    (data.general_reasoning === 'low' || data.general_reasoning === 'high')
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
    (change.show_resource_chart !== undefined && data.show_resource_chart !== change.show_resource_chart)
  )) {
    throw new Error('La confirmation ne correspond pas au choix envoyé. Rechargez les paramètres.')
  }
  return data
}

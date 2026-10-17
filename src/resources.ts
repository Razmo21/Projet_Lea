export type MemoryReading = { total_bytes: number; used_bytes: number; available_bytes: number }
export type ResourceSnapshot = {
  active: boolean
  stale: boolean
  profile_id?: string
  sampled_at?: number
  ram?: MemoryReading | null
  cpu_percent?: number | null
  vram?: MemoryReading | null
  level?: 'NORMAL' | 'WARNING' | 'CRITICAL'
  messages?: string[]
}

// Une mesure inconnue reste nulle, et ne devient jamais une barre à zéro.
function validMemory(value: unknown): boolean {
  if (value === null) return true
  if (typeof value !== 'object' || !value) return false
  const item = value as MemoryReading
  return [item.total_bytes, item.used_bytes, item.available_bytes].every(Number.isFinite) &&
    item.total_bytes > 0 && item.used_bytes >= 0 && item.available_bytes >= 0 &&
    Math.abs(item.used_bytes + item.available_bytes - item.total_bytes) < 1
}

// Ne présente jamais un payload incomplet comme un état de santé confirmé.
export function isResourceSnapshot(value: unknown): value is ResourceSnapshot {
  if (typeof value !== 'object' || !value) return false
  const item = value as ResourceSnapshot
  if (typeof item.active !== 'boolean' || typeof item.stale !== 'boolean') return false
  if (item.stale) return true
  return typeof item.profile_id === 'string' && item.profile_id.length > 0 &&
    Number.isFinite(item.sampled_at) && validMemory(item.ram) && validMemory(item.vram) &&
    (item.cpu_percent === null || (typeof item.cpu_percent === 'number' && Number.isFinite(item.cpu_percent) && item.cpu_percent >= 0 && item.cpu_percent <= 100)) &&
    ['NORMAL', 'WARNING', 'CRITICAL'].includes(item.level ?? '') &&
    Array.isArray(item.messages) && item.messages.every((message) => typeof message === 'string')
}

// Les avertissements d'un ancien profil ne doivent pas survivre à sa commutation.
export function resourcesForProfile(snapshot: ResourceSnapshot | null, profileId?: string): ResourceSnapshot | null {
  return snapshot?.active && !snapshot.stale && snapshot.profile_id === profileId ? snapshot : null
}

// Les alertes restent indépendantes de la préférence d'affichage du diagramme.
export function resourceNotice(snapshot: ResourceSnapshot | null): string {
  if (!snapshot || snapshot.stale) return 'Surveillance indisponible ou en attente ; l’état des ressources n’est pas confirmé.'
  return snapshot.messages?.join(' ') ?? ''
}

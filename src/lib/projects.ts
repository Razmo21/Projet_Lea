export type ProjectSummary = {
  id: string
  name: string
  relative_path: string
  created_at: string
  updated_at: string
  active: boolean
}

export type ProjectCatalog = {
  projects: ProjectSummary[]
  active_project_id: string | null
}

// Valide la réponse publique sans jamais accepter un chemin absolu côté UI.
export function isProjectCatalog(value: unknown): value is ProjectCatalog {
  if (typeof value !== 'object' || value === null) return false
  const catalog = value as Record<string, unknown>
  if (
    !Array.isArray(catalog.projects) ||
    (catalog.active_project_id !== null && typeof catalog.active_project_id !== 'string')
  ) return false
  return catalog.projects.every((item) => {
    if (typeof item !== 'object' || item === null) return false
    const project = item as Record<string, unknown>
    return (
      typeof project.id === 'string' &&
      typeof project.name === 'string' &&
      typeof project.relative_path === 'string' &&
      !/^(?:[a-z]:|[\\/])/i.test(project.relative_path) &&
      typeof project.created_at === 'string' &&
      typeof project.updated_at === 'string' &&
      typeof project.active === 'boolean'
    )
  })
}

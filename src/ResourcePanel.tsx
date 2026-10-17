import { useEffect, useState } from 'react'
import { backendOrigin } from './conversations'
import { isResourceSnapshot, resourceNotice, resourcesForProfile } from './resources'
import type { MemoryReading, ResourceSnapshot } from './resources'

// Une petite barre conserve l'unité et distingue explicitement l'absence de mesure.
function MemoryBar({ label, value }: { label: string; value?: MemoryReading | null }) {
  // L'unité binaire correspond aux octets mesurés par Windows et NVIDIA.
  const gib = (bytes: number) => (bytes / 1024 ** 3).toFixed(1)
  return (
    <div className="resource-row">
      <span>{label}</span>
      {value ? (
        <>
          <span>{gib(value.used_bytes)} / {gib(value.total_bytes)} Gio</span>
          <progress aria-label={label} value={value.used_bytes} max={value.total_bytes} />
        </>
      ) : <span>Indisponible</span>}
    </div>
  )
}

// Le navigateur lit un snapshot : la supervision appartient uniquement au backend.
export default function ResourcePanel({ enabled, showChart, profileId }: {
  enabled: boolean; showChart: boolean; profileId?: string
}) {
  const [snapshot, setSnapshot] = useState<ResourceSnapshot | null>(null)
  // Désactiver la vue interrompt sa lecture, sans agir sur la supervision serveur.
  useEffect(() => {
    setSnapshot(null)
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    let timer: number | undefined

    // Un prochain polling n'est planifié qu'après la fin de celui-ci.
    async function poll() {
      try {
        const response = await fetch(`${backendOrigin}/api/resources`, {
          cache: 'no-store', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        })
        const value: unknown = await response.json()
        if (!response.ok || !isResourceSnapshot(value)) throw new Error('Mesures invalides')
        if (!controller.signal.aborted) setSnapshot(value)
      } catch {
        if (!controller.signal.aborted) setSnapshot(null)
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(() => void poll(), 10_000)
      }
    }
    void poll()
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [enabled, profileId])

  const current = enabled ? resourcesForProfile(snapshot, profileId) : null
  const notice = enabled ? resourceNotice(current) : ''
  return (
    <aside className="resources" aria-label="Ressources de Léa">
      {notice && (
        <p
          role={current?.level === 'CRITICAL' ? 'alert' : 'status'}
          className={current?.level === 'CRITICAL' ? 'status-error' : 'status-warning'}
        >
          {notice}
        </p>
      )}
      {showChart && (
        <section className="resource-chart" aria-label="Diagramme des ressources">
          <h2>Ressources</h2>
          {!enabled && <p>Surveillance inactive lorsque Léa est arrêtée.</p>}
          <MemoryBar label="RAM" value={current?.ram} />
          <div className="resource-row">
            <span>CPU</span>
            {current?.cpu_percent != null ? (
              <>
                <span>{current.cpu_percent.toFixed(0)} %</span>
                <progress aria-label="CPU" value={current.cpu_percent} max={100} />
              </>
            ) : <span>Indisponible</span>}
          </div>
          <MemoryBar label="VRAM" value={current?.vram} />
        </section>
      )}
    </aside>
  )
}

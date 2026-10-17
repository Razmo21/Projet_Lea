import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { requestPreferences } from './preferences'
import type { Preferences, ReasoningLevel } from './preferences'

type SettingsProps = { onBack: () => void; onSaved: (preferences: Preferences) => void }

// Vue indépendante des conversations ; seul le choix confirmé vient de la persistance.
export default function Settings({ onBack, onSaved }: SettingsProps) {
  const [saved, setSaved] = useState<Preferences | null>(null)
  const [draft, setDraft] = useState<ReasoningLevel>('low')
  const [chartDraft, setChartDraft] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [reload, setReload] = useState(0)
  const savingLock = useRef(false)
  const title = useRef<HTMLHeadingElement>(null)
  const dirty = saved !== null && (draft !== saved.general_reasoning || chartDraft !== saved.show_resource_chart)

  // Place le clavier dans cette vue sans déplacer le focus à chaque changement de valeur.
  useEffect(() => { title.current?.focus() }, [])

  // Ignore une réponse tardive après fermeture ou nouvelle tentative de chargement.
  useEffect(() => {
    let current = true
    setLoading(true)
    setSaved(null)
    setError('')
    setConfirmation('')
    void requestPreferences().then((value) => {
      if (!current) return
      setSaved(value)
      setDraft(value.general_reasoning)
      setChartDraft(value.show_resource_chart)
    }).catch((failure: unknown) => {
      if (current) setError(failure instanceof Error ? failure.message : 'Paramètres indisponibles.')
    }).finally(() => {
      if (current) setLoading(false)
    })
    return () => { current = false }
  }, [reload])

  // Le brouillon ne remplace la valeur enregistrée qu'après une confirmation cohérente.
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!saved || !dirty || savingLock.current || loading) return
    savingLock.current = true
    setSaving(true)
    setError('')
    setConfirmation('')
    try {
      const confirmed = await requestPreferences({
        expected_revision: saved.revision,
        ...(draft !== saved.general_reasoning ? { general_reasoning: draft } : {}),
        ...(chartDraft !== saved.show_resource_chart ? { show_resource_chart: chartDraft } : {}),
      })
      setSaved(confirmed)
      setDraft(confirmed.general_reasoning)
      setChartDraft(confirmed.show_resource_chart)
      onSaved(confirmed)
      setConfirmation('Paramètres enregistrés. L’affichage s’applique immédiatement ; le raisonnement à la prochaine réponse Général.')
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Enregistrement non confirmé.')
    } finally {
      savingLock.current = false
      setSaving(false)
    }
  }

  // Un choix non validé peut être abandonné, mais jamais pendant une sauvegarde en vol.
  function back() {
    if (savingLock.current) return
    if (dirty && !window.confirm('Quitter les paramètres sans enregistrer les modifications ?')) return
    onBack()
  }

  // Modifier la sélection efface une ancienne confirmation qui ne concerne plus ce brouillon.
  function select(level: ReasoningLevel) {
    setDraft(level)
    setConfirmation('')
  }

  return (
    <section className="chat settings" aria-labelledby="settings-title" aria-busy={loading || saving}>
      <div className="page-header">
        <h1 id="settings-title" ref={title} tabIndex={-1}>Paramètres de Léa</h1>
        <button type="button" className="secondary-button" onClick={back} disabled={saving}>
          Retour aux conversations
        </button>
      </div>
      <p className="settings-description">
        Vos préférences restent disponibles lorsque l’IA est arrêtée.
        Les changements ne coupent ni une réponse ni un run en cours.
      </p>
      {loading && <p role="status">Chargement des paramètres…</p>}
      {saved && (
        <form onSubmit={(event) => void save(event)}>
          <fieldset disabled={loading || saving || !saved.general_reasoning_available} className="settings-group">
            <legend>Général — Raisonnement</legend>
            <p id="reasoning-help">Low donne une réponse directe. High active la réflexion interne, sans l’afficher.</p>
            {!saved.general_reasoning_available && (
              <p role="status">
                Indisponible avec le modèle Général configuré. Le choix mémorisé reste conservé, mais n’est pas appliqué.
              </p>
            )}
            <div className="reasoning-options" aria-describedby="reasoning-help">
              <label>
                <input type="radio" name="reasoning" value="low" checked={draft === 'low'} onChange={() => select('low')} />
                Low — Direct
              </label>
              <label>
                <input type="radio" name="reasoning" value="high" checked={draft === 'high'} onChange={() => select('high')} />
                High — Réflexion
              </label>
            </div>
            <p>Enregistré : {saved.general_reasoning === 'low' ? 'Low' : 'High'}.</p>
            {dirty && <p className="status-warning">Modification non enregistrée.</p>}
          </fieldset>
          <fieldset disabled={loading || saving} className="settings-group">
            <legend>Ressources</legend>
            <label className="resource-option">
              <input type="checkbox" checked={chartDraft} onChange={(event) => {
                // Le choix reste provisoire jusqu'au commit confirmé.
                setChartDraft(event.target.checked)
                setConfirmation('')
              }} />
              Afficher le diagramme des ressources
            </label>
            <p>La surveillance reste active avec tout profil IA, même diagramme masqué. Les alertes ne coupent jamais une réponse ni un run.</p>
          </fieldset>
          <button type="submit" disabled={!dirty || loading || saving}>
            {saving ? 'Enregistrement…' : 'Valider'}
          </button>
        </form>
      )}
      {confirmation && <p className="status-ready" role="status">{confirmation}</p>}
      <section className="settings-group" aria-labelledby="programming-settings-title">
        <h2 id="programming-settings-title">Programmation</h2>
        <p>Aucun réglage Low / High n’est proposé : aucun mécanisme compatible suffisamment fiable n’a été validé pour ce profil.</p>
        <p>Le traitement OpenHands reste inchangé, avec ses contrôles de sécurité, ses tests et ses checkpoints. Le choix Général ne modifie pas un run.</p>
      </section>
      {error && (
        <div role="alert">
          <p className="status-error">{error}</p>
          <button type="button" className="secondary-button" disabled={saving || loading} onClick={() => setReload((value) => value + 1)}>
            Recharger les paramètres
          </button>
        </div>
      )}
    </section>
  )
}

import type { ReactNode } from 'react'
import type { AgentRun } from '../lib/agentRuns'
import { agentRunValidationPresentation, isActiveAgentRun } from '../lib/agentRuns'
import MarkdownMessage from './MarkdownMessage'
import { shortNotice } from '../lib/notices'

// Le résultat reste lisible après une décision de checkpoint, même sans fichier modifié.
// Seuls les champs reçus du backend sont affichés ; un échec ne devient jamais un succès.
export default function AgentRunResult({ run, children }: {
  run: AgentRun
  children?: ReactNode
}) {
  const active = isActiveAgentRun(run)
  const summary = run.result_summary?.trim()
  const failure = run.failure_detail?.trim()
  const validation = agentRunValidationPresentation(run)
  const failed = !active && run.state !== 'completed'
  const status = run.state === 'cancelled'
    ? 'Tâche annulée.'
    : run.state === 'limit_reached'
      ? 'La tâche a atteint sa limite.'
      : 'La tâche a échoué.'

  return (
    <article className="agent-result message message-assistant" aria-label="Résultat de la tâche">
      <strong>Léa</strong>
      <small className="message-profile">Programmation</small>
      {active && <p role="status">Tâche en cours…</p>}
      {failed && <p className="status-error" role="status">{shortNotice(status, 'task')}</p>}
      {!active && summary && <MarkdownMessage content={summary} />}
      {!active && failure && <p className="status-error">{shortNotice(failure, 'task')}</p>}
      {!active && !summary && !failure && (
        <p>Aucune réponse finale</p>
      )}
      {!active && !failed && !validation.accepts_changes && (
        <p className={`status-${validation.tone}`}>{shortNotice(validation.message, 'task')}</p>
      )}
      {children}
    </article>
  )
}

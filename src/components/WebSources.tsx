import type { WebSource } from '../lib/conversations'
import { webSourceKindLabel } from '../lib/conversations'
import { publicLink } from './MarkdownMessage'

// Les références viennent uniquement du backend ; le Markdown n'en crée aucune.
export default function WebSources({ sources }: { sources: WebSource[] }) {
  if (!sources.length) return null
  return (
    <details className="message-sources">
      <summary>
        Web utilisé · {sources.length} source{sources.length > 1 ? 's' : ''}{' '}
        collectée{sources.length > 1 ? 's' : ''}
      </summary>
      <section aria-label="Sources Web collectées">
        <p>Références contrôlées par Léa</p>
        <ol>
          {sources.map((source) => {
            const href = publicLink(source.url)
            const title = `[${source.source_id}] ${source.title}`
            return (
              <li key={`${source.source_id}:${source.url}`}>
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    referrerPolicy="no-referrer"
                  >
                    {title}
                  </a>
                ) : (
                  <span>{title}</span>
                )}
                <small>
                  {source.domain} · {source.provider} ·{' '}
                  {webSourceKindLabel(source)}
                </small>
                <small>
                  Consulté : {source.consulted_at}
                  {source.published_at
                    ? ` · publié : ${source.published_at}`
                    : ''}
                  {source.updated_at
                    ? ` · mis à jour : ${source.updated_at}`
                    : ''}
                  {source.document_date
                    ? ` · date interne du document : ${source.document_date}`
                    : ''}
                </small>
                {source.limitations && (
                  <small>Limite : {source.limitations}</small>
                )}
              </li>
            )
          })}
        </ol>
      </section>
    </details>
  )
}

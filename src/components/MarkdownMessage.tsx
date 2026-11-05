import { memo, useState } from 'react'
import type { ReactNode } from 'react'
import Markdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

type CodeBlockProps = { children: ReactNode; text: string; language: string }

// Aucun schéma exécutable, chemin local, identifiant ou URL relative n'est activé.
export function publicLink(value: string): string | undefined {
  try {
    const url = new URL(value)
    if (
      !['https:', 'http:'].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return undefined
    return url.href
  } catch {
    return undefined
  }
}

// La copie utilise le contenu du bloc, jamais son titre ni le texte de la réponse.
function CodeBlock({ children, text, language }: CodeBlockProps) {
  const [feedback, setFeedback] = useState('')

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(text)
      setFeedback('Code copié.')
    } catch {
      setFeedback('Copie automatique impossible')
    }
  }

  return (
    <div className="code-block">
      <div className="code-toolbar">
        <span>{language || 'Code'}</span>
        <button
          type="button"
          className="text-button"
          onClick={() => void copyCode()}
        >
          Copier le code
        </button>
      </div>
      <pre
        tabIndex={0}
        aria-label={language ? `Code ${language}` : 'Bloc de code'}
      >
        {children}
      </pre>
      {feedback && (
        <small className="code-feedback" role="status">
          {feedback}
        </small>
      )}
    </div>
  )
}

const components: Components = {
  // Seule une ouverture explicite peut quitter l'interface ; aucun chargement au rendu.
  a({ href, children }) {
    const safe = href && publicLink(href)
    return safe ? (
      <a
        href={safe}
        target="_blank"
        rel="noopener noreferrer"
        referrerPolicy="no-referrer"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    )
  },
  // Un message ne doit pas déclencher de requête distante pour afficher une image.
  img({ alt }) {
    return (
      <span className="image-placeholder">
        [Image non chargée{alt ? ` : ${alt}` : ''}]
      </span>
    )
  },
  // Le texte de l'arbre syntaxique exclut les délimiteurs et conserve le code littéral.
  pre({ children, node }) {
    const code = node?.children.find(
      (child) => child.type === 'element' && child.tagName === 'code',
    )
    const text =
      code?.type === 'element'
        ? code.children
            .map((child) => (child.type === 'text' ? child.value : ''))
            .join('')
        : ''
    const classes = code?.type === 'element' ? code.properties.className : []
    const language = Array.isArray(classes)
      ? String(
          classes.find((name) => String(name).startsWith('language-')) ?? '',
        ).slice(9)
      : ''
    return (
      <CodeBlock key={text} text={text} language={language}>
        {children}
      </CodeBlock>
    )
  },
  // Le défilement appartient au tableau, y compris au clavier, pas à toute la page.
  table({ children }) {
    return (
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Tableau défilant"
      >
        <table>{children}</table>
      </div>
    )
  },
}

// CommonMark/GFM interprète une seule fois le texte brut. Pas de réécriture des
// antislashs : les chemins, expressions régulières et exemples restent fidèles.
const MarkdownMessage = memo(function MarkdownMessage({
  content,
}: {
  content: string
}) {
  return (
    <div className="markdown-content">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={components}
        skipHtml
        urlTransform={(url) => publicLink(url) ?? ''}
      >
        {content}
      </Markdown>
    </div>
  )
})

export default MarkdownMessage

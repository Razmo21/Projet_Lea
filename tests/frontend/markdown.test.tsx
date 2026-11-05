import assert from 'node:assert/strict'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import MarkdownMessage, {
  publicLink,
} from '../../src/components/MarkdownMessage'
import WebSources from '../../src/components/WebSources'
import type { WebSource } from '../../src/lib/conversations'

// Le rendu serveur emprunte le même arbre React que l'historique du navigateur.
function render(content: string) {
  return renderToStaticMarkup(<MarkdownMessage content={content} />)
}

test('Markdown : titres, emphases, listes imbriquées, citation, tâches et séparateur', () => {
  const html = render(
    '# Titre\n\n## Suite\n\n**gras** *italique* ~~barré~~\n\n- parent\n  - enfant\n\n1. premier\n2. second\n\n> citation\n\n- [x] fait\n- [ ] à faire\n\n---',
  )
  for (const fragment of [
    '<h1>Titre</h1>',
    '<h2>Suite</h2>',
    '<strong>gras</strong>',
    '<em>italique</em>',
    '<del>barré</del>',
    '<ol>',
    '<blockquote>',
    'type="checkbox"',
    'disabled=""',
    '<hr/>',
  ])
    assert.ok(html.includes(fragment), fragment)
  assert.equal((html.match(/<ul/g) ?? []).length, 3)
})

test('Tableaux, paragraphes, saut explicite, Unicode et liens HTTPS', () => {
  const html = render(
    '| État | Valeur |\n| --- | --- |\n| Québec | 4 °C 🐾 |\n\nUne ligne  \nsuivante\n\n[Source](https://example.org/page)',
  )
  for (const fragment of [
    '<table>',
    '<th>État</th>',
    '<td>4 °C 🐾</td>',
    '<br/>',
    'href="https://example.org/page"',
    'noopener noreferrer',
  ])
    assert.ok(html.includes(fragment))
})

test('Pas de double échappement ni de réécriture des littéraux', () => {
  assert.ok(render('**bonjour**').includes('<strong>bonjour</strong>'))
  assert.ok(render('\\*\\*bonjour\\*\\*').includes('<p>**bonjour**</p>'))
  const html = render(
    '**été** &amp; \\*littéral\\*\n\n`C:\\Users\\lea`\n\n```python\nprint("\\n")\nregex = r"\\d+"\n```',
  )
  assert.ok(html.includes('<strong>été</strong> &amp; *littéral*'))
  assert.ok(html.includes('<code>C:\\Users\\lea</code>'))
  assert.ok(html.includes('print(&quot;\\n&quot;)'))
  assert.ok(html.includes('regex = r&quot;\\d+&quot;'))
  assert.ok(!html.includes('&amp;amp;'))
  assert.ok(html.includes('Copier le code'))
  assert.ok(html.includes('language-python'))
})

test('Markdown incomplet, code sans langage et texte long restent affichables', () => {
  const html = render(
    '**incomplet\n\n```\n<div>texte littéral</div>\n' + 'x'.repeat(20000),
  )
  assert.ok(html.includes('**incomplet'))
  assert.ok(html.includes('&lt;div&gt;texte littéral&lt;/div&gt;'))
  assert.ok(html.includes('x'.repeat(20000)))
})

test('HTML, événements, schémas actifs et images distantes sont inertes', () => {
  const html = render(
    '<script>alert(1)</script>\n\n<img src="https://host/track" onerror="alert(1)">\n\n[attaque](javascript:alert%281%29) [fichier](file:///C:/private)\n\n![image](https://host/track)',
  )
  assert.ok(!html.includes('<script'))
  assert.ok(!html.includes('<img'))
  assert.ok(!html.includes('href='))
  assert.ok(!html.includes('onerror'))
  assert.ok(html.includes('Image non chargée'))
  for (const url of [
    'javascript:alert(1)',
    'data:text/html,test',
    'file:///x',
    '/api/core/start',
    '//example.org',
    'https://user:secret@example.org',
  ])
    assert.equal(publicLink(url), undefined)
})

test('Les marqueurs seuls ne créent jamais de source ; métadonnées backend fidèles', () => {
  assert.ok(!render('Fait [S999]').includes('<a'))
  const source: WebSource = {
    source_id: 'S1',
    title: 'Document',
    url: 'https://example.org/',
    domain: 'example.org',
    snippet: '',
    provider: 'direct',
    consulted_at: '2026-11-01',
    published_at: '2025-01-01',
    updated_at: null,
    document_date: null,
    retrieval_status: 'snippet_only',
    source_kind: 'search_snippet',
    limitations: 'Page non lue',
  }
  const html = renderToStaticMarkup(<WebSources sources={[source]} />)
  assert.ok(html.includes('[S1] Document'))
  assert.ok(html.includes('extrait du moteur seulement'))
  assert.ok(html.includes('Page non lue'))
  assert.ok(html.includes('2026-11-01'))
  assert.ok(!renderToStaticMarkup(<WebSources sources={[]} />))
})

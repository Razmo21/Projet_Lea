import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'


const cdpPort = Number(process.env.LEA_EDGE_CDP_PORT ?? '9228')
const appUrl = 'http://127.0.0.1:5173'
const databasePath = process.env.LEA_EDGE_DB_PATH
const timeoutMs = 150_000
const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class CdpSession {
  constructor(webSocketUrl, name) {
    this.webSocketUrl = webSocketUrl
    this.name = name
    this.nextId = 1
    this.pending = new Map()
    this.events = []
  }

  async connect() {
    this.socket = new WebSocket(this.webSocketUrl)
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true })
      this.socket.addEventListener('error', reject, { once: true })
    })
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data))
      if (message.id) {
        const callback = this.pending.get(message.id)
        if (callback) {
          this.pending.delete(message.id)
          if (message.error) callback.reject(new Error(message.error.message))
          else callback.resolve(message.result)
        }
        return
      }
      this.events.push(message)
    })
    await Promise.all([
      this.send('Runtime.enable'),
      this.send('Page.enable'),
      this.send('Network.enable'),
      this.send('Log.enable'),
    ])
  }

  send(method, params = {}) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  async evaluate(expression) {
    const response = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    })
    if (response.exceptionDetails) {
      throw new Error(
        response.exceptionDetails.exception?.description ??
          response.exceptionDetails.text ??
          'Évaluation JavaScript échouée.',
      )
    }
    return response.result.value
  }

  async waitFor(expression, description, timeout = timeoutMs) {
    const deadline = Date.now() + timeout
    let lastValue
    while (Date.now() < deadline) {
      try {
        lastValue = await this.evaluate(expression)
        if (lastValue) return lastValue
      } catch {
        // La page peut être brièvement indisponible pendant un rechargement.
      }
      await sleep(250)
    }
    throw new Error(`${this.name}: délai dépassé pour ${description}; dernière valeur=${lastValue}`)
  }

  async trustedClick(selector, text) {
    // Après un rechargement ou un changement d'onglet, Edge peut conserver la
    // cible CDP attachée sans lui distribuer les événements Input. L'activation
    // explicite garde le clic réellement piloté par Edge (et non element.click).
    await this.send('Page.bringToFront')
    await sleep(250)
    const point = await this.evaluate(`(() => {
      const candidates = [...document.querySelectorAll(${JSON.stringify(selector)})];
      const element = candidates.find((candidate) =>
        candidate.textContent.trim() === ${JSON.stringify(text)} ||
        candidate.querySelector('span')?.textContent.trim() === ${JSON.stringify(text)}
      );
      if (!element || element.disabled) return null;
      element.scrollIntoView({ block: 'center', inline: 'center' });
      const rect = element.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    })()`)
    assert.ok(point, `${this.name}: bouton « ${text} » absent ou désactivé`)
    await this.send('Input.dispatchMouseEvent', {
      type: 'mousePressed',
      x: point.x,
      y: point.y,
      button: 'left',
      clickCount: 1,
    })
    await this.send('Input.dispatchMouseEvent', {
      type: 'mouseReleased',
      x: point.x,
      y: point.y,
      button: 'left',
      clickCount: 1,
    })
  }

  async setValue(selector, value) {
    const changed = await this.evaluate(`(() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return false;
      const prototype = element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
      setter.call(element, ${JSON.stringify(value)});
      element.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    })()`)
    assert.equal(changed, true, `${this.name}: champ ${selector} absent`)
  }

  close() {
    this.socket.close()
  }
}

async function targets() {
  const response = await fetch(`http://127.0.0.1:${cdpPort}/json/list`)
  assert.equal(response.ok, true, 'Liste CDP inaccessible')
  return response.json()
}

function databaseRows(sql, parameters = []) {
  assert.ok(databasePath, 'LEA_EDGE_DB_PATH doit désigner la base Edge isolée.')
  const code = [
    'import json, sqlite3, sys',
    'connection = sqlite3.connect(sys.argv[1])',
    'rows = connection.execute(sys.argv[2], json.loads(sys.argv[3])).fetchall()',
    'connection.close()',
    'print(json.dumps(rows))',
  ].join('; ')
  const result = spawnSync(
    'backend\\.venv\\Scripts\\python.exe',
    ['-c', code, databasePath, sql, JSON.stringify(parameters)],
    { cwd: process.cwd(), encoding: 'utf8' },
  )
  assert.equal(result.status, 0, result.stderr)
  return JSON.parse(result.stdout)
}

async function connectPage(targetId, name) {
  const target = (await targets()).find((candidate) => candidate.id === targetId)
  assert.ok(target?.webSocketDebuggerUrl, `${name}: cible Edge introuvable`)
  const session = new CdpSession(target.webSocketDebuggerUrl, name)
  await session.connect()
  return session
}

async function primaryPage() {
  const target = (await targets()).find(
    (candidate) => candidate.type === 'page' && candidate.url.startsWith(appUrl),
  )
  assert.ok(target, 'La page Léa est absente dans Edge Stable')
  return connectPage(target.id, 'onglet 1')
}

function messagesExpression() {
  return `[...document.querySelectorAll('.message')].map((message) => ({
    role: message.classList.contains('message-user') ? 'user' : 'assistant',
    status: ['pending', 'completed', 'failed'].find((state) => message.classList.contains('message-' + state)) ?? null,
    content: message.querySelector(':scope > p')?.textContent ?? ''
  }))`
}

async function sendMessage(page, message, expectedMessageCount, expectedAnswer) {
  await page.setValue('#question', message)
  await page.trustedClick('button', 'Envoyer')
  const result = await page.waitFor(
    `(() => {
      const items = ${messagesExpression()};
      const loading = document.body.innerText.includes('Léa répond…');
      return !loading && items.length === ${expectedMessageCount} ? items : null;
    })()`,
    `la réponse au message « ${message.slice(0, 30)} »`,
  )
  if (expectedAnswer) {
    assert.match(result.at(-1).content, expectedAnswer)
  }
  return result
}

const page = await primaryPage()
let secondPage

try {
  await page.waitFor(
    `document.body.innerText.includes('Léa est arrêtée.')`,
    "l’état initial arrêté",
    30_000,
  )
  assert.equal(
    await page.evaluate(`document.querySelectorAll('.conversation-summary').length`),
    0,
    'Une base isolée doit commencer sans conversation.',
  )

  await page.trustedClick('button', 'Démarrer Léa')
  await page.waitFor(
    `document.body.innerText.includes('Léa est prête.')`,
    'le démarrage du cœur',
  )

  await sendMessage(
    page,
    "Mon animal de test s'appelle Rex. Réponds seulement par OK.",
    2,
    /OK/i,
  )
  await sendMessage(
    page,
    "Comment s'appelle mon animal de test ? Réponds seulement par son nom.",
    4,
    /Rex/i,
  )
  const conversationId = await page.evaluate(
    `new URL(location.href).searchParams.get('conversation')`,
  )
  assert.match(conversationId, /^[0-9a-f-]{36}$/i)

  await page.send('Page.reload', { ignoreCache: true })
  await page.waitFor(
    `document.body.innerText.includes('Rex') && document.querySelectorAll('.message').length === 4`,
    'la restauration après actualisation',
  )

  await page.trustedClick('button', 'Arrêter Léa')
  await page.waitFor(
    `document.body.innerText.includes('Léa est arrêtée.')`,
    "l’arrêt du cœur en conservant Vite",
  )
  assert.equal(
    await page.evaluate(`document.querySelectorAll('.message').length`),
    4,
    'Les messages visibles doivent rester pendant l’arrêt du cœur.',
  )

  await page.trustedClick('button', 'Démarrer Léa')
  await page.waitFor(
    `document.body.innerText.includes('Léa est prête.') && document.querySelectorAll('.message').length === 4`,
    'la restauration après redémarrage du cœur',
  )
  await sendMessage(
    page,
    "Rappelle seulement le nom de mon animal de test.",
    6,
    /Rex/i,
  )

  await page.trustedClick('button', 'Renommer')
  await page.waitFor(
    `!!document.querySelector('#conversation-title')`,
    "l'ouverture de l'éditeur de titre",
  )
  await page.trustedClick('.message-user button', 'Modifier')
  assert.equal(
    await page.evaluate(`!!document.querySelector('#conversation-title')`),
    false,
    "L'éditeur de message doit fermer l'éditeur de titre.",
  )
  await page.setValue(
    '.message-editor textarea',
    "Mon animal de test s'appelle Moka. Réponds seulement par OK.",
  )
  await page.trustedClick('.message-editor button', 'Enregistrer et régénérer')
  await page.waitFor(
    `(() => { const items = ${messagesExpression()}; return items.length === 2 && items[0].content.includes('Moka') && !document.body.innerText.includes('Léa répond…'); })()`,
    'la modification destructive du premier message',
  )
  assert.deepEqual(
    databaseRows(
      'SELECT position, role, content, status FROM messages WHERE conversation_id = ? ORDER BY position',
      [conversationId],
    ).map(([position, role, content, status]) => [position, role, content, status]),
    [
      [1, 'user', "Mon animal de test s'appelle Moka. Réponds seulement par OK.", 'completed'],
      [2, 'assistant', databaseRows(
        'SELECT content FROM messages WHERE conversation_id = ? AND position = 2',
        [conversationId],
      )[0][0], 'completed'],
    ],
    'SQLite doit contenir uniquement la question modifiée et sa nouvelle réponse.',
  )

  const assistantBeforeRegeneration = await page.evaluate(
    `document.querySelector('.message-assistant > p')?.textContent ?? ''`,
  )
  await page.trustedClick('.message-assistant button', 'Régénérer')
  await page.waitFor(
    `document.querySelectorAll('.message').length === 2 && !document.body.innerText.includes('Léa répond…')`,
    'la régénération destructive',
  )
  const assistantAfterRegeneration = await page.evaluate(
    `document.querySelector('.message-assistant > p')?.textContent ?? ''`,
  )
  assert.ok(assistantBeforeRegeneration.length > 0 && assistantAfterRegeneration.length > 0)

  await page.setValue(
    '#question',
    'Écris exactement 200 mots simples sur les arbres, sans liste.',
  )
  await page.trustedClick('button', 'Envoyer')
  await page.waitFor(
    `document.body.innerText.includes('Léa répond…')`,
    'le début de la génération à interrompre',
  )
  await sleep(200)
  await page.trustedClick('button', 'Arrêter Léa')
  await page.waitFor(
    `document.body.innerText.includes('Léa est arrêtée.')`,
    "l’arrêt pendant une génération",
  )
  await page.trustedClick('button', 'Démarrer Léa')
  await page.waitFor(
    `document.body.innerText.includes('Léa est prête.') && !!document.querySelector('.message-failed')`,
    'la récupération de la question interrompue',
  )
  assert.equal(
    await page.evaluate(`document.querySelectorAll('.message-assistant').length`),
    1,
    'Aucun faux assistant ne doit être créé après interruption.',
  )
  await page.trustedClick('.message-failed button', 'Réessayer')
  await page.waitFor(
    `!document.querySelector('.message-failed') && document.querySelectorAll('.message').length === 4 && !document.body.innerText.includes('Léa répond…')`,
    'le réessai de la question interrompue',
  )

  const copyButton = await page.evaluate(`(() => {
    const buttons = [...document.querySelectorAll('.message-assistant .text-button')].filter((button) => button.textContent.trim() === 'Copier');
    buttons.at(-1).scrollIntoView({ block: 'center', inline: 'center' });
    const rect = buttons.at(-1).getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  })()`)
  await page.send('Input.dispatchMouseEvent', { type: 'mousePressed', ...copyButton, button: 'left', clickCount: 1 })
  await page.send('Input.dispatchMouseEvent', { type: 'mouseReleased', ...copyButton, button: 'left', clickCount: 1 })
  await page.waitFor(
    `document.querySelector('.copy-feedback')?.textContent.includes('copié')`,
    'la copie du message visible',
    10_000,
  )

  await page.trustedClick('button', 'Renommer')
  await page.setValue('#conversation-title', 'Mémoire Moka spéciale')
  await page.trustedClick('.rename-editor button', 'Enregistrer')
  await page.waitFor(
    `document.querySelector('.conversation-header h2')?.textContent === 'Mémoire Moka spéciale'`,
    'le renommage',
  )

  await page.setValue('#conversation-search', 'MÉMOIRE MOKA')
  await page.waitFor(
    `document.querySelectorAll('.conversation-summary').length === 1 && document.querySelector('.conversation-summary')?.textContent.includes('Mémoire Moka spéciale')`,
    'la recherche locale insensible à la casse',
  )
  await page.trustedClick('.conversation-summary', 'Mémoire Moka spéciale')

  const listCountBeforeNew = await page.evaluate(
    `document.querySelectorAll('.conversation-summary').length`,
  )
  await page.trustedClick('button', 'Renommer')
  await page.waitFor(
    `!!document.querySelector('#conversation-title')`,
    "l'ouverture du renommage avant navigation",
  )
  await page.trustedClick('button', 'Nouvelle conversation')
  assert.equal(
    await page.evaluate(`!!document.querySelector('#conversation-title')`),
    false,
    'Une navigation doit fermer le brouillon de renommage.',
  )
  assert.equal(
    await page.evaluate(`document.querySelectorAll('.conversation-summary').length`),
    listCountBeforeNew,
    'Une nouvelle conversation vide ne doit pas être persistée.',
  )
  await page.trustedClick('.conversation-summary', 'Mémoire Moka spéciale')

  const created = await page.send('Target.createTarget', {
    url: `${appUrl}/?conversation=${conversationId}`,
    background: false,
  })
  secondPage = await connectPage(created.targetId, 'onglet 2')
  await secondPage.waitFor(
    `document.querySelector('.conversation-header h2')?.textContent === 'Mémoire Moka spéciale'`,
    'le chargement de la conversation dans le second onglet',
  )

  await page.trustedClick('button', 'Renommer')
  await page.setValue('#conversation-title', 'Titre du premier onglet')
  await page.trustedClick('.rename-editor button', 'Enregistrer')
  await page.waitFor(
    `document.querySelector('.conversation-header h2')?.textContent === 'Titre du premier onglet'`,
    'la mutation du premier onglet',
  )

  await secondPage.trustedClick('button', 'Renommer')
  await secondPage.setValue('#conversation-title', 'Titre périmé du second onglet')
  await secondPage.trustedClick('.rename-editor button', 'Enregistrer')
  await secondPage.waitFor(
    `document.querySelector('[role=alert]')?.textContent.includes('autre fenêtre') && document.querySelector('.conversation-header h2')?.textContent === 'Titre du premier onglet'`,
    'le conflit de révision dans le second onglet',
  )

  await page.evaluate(`window.confirm = () => true`)
  await page.trustedClick('button', 'Supprimer')
  await page.waitFor(
    `document.querySelector('.conversation-header h2')?.textContent === 'Nouvelle conversation' && document.querySelectorAll('.conversation-summary').length === 0`,
    'la suppression confirmée avec cascade',
  )
  assert.deepEqual(
    databaseRows('SELECT COUNT(*) FROM conversations WHERE id = ?', [conversationId]),
    [[0]],
  )
  assert.deepEqual(
    databaseRows('SELECT COUNT(*) FROM messages WHERE conversation_id = ?', [conversationId]),
    [[0]],
  )

  const storage = await page.evaluate(`(async () => ({
    localStorage: localStorage.length,
    sessionStorage: sessionStorage.length,
    indexedDb: (await indexedDB.databases()).length,
    body: document.body.innerText
  }))()`)
  assert.equal(storage.localStorage, 0)
  assert.equal(storage.sessionStorage, 0)
  assert.equal(storage.indexedDb, 0)
  assert.doesNotMatch(storage.body, /\/no_think|<\s*\/?\s*think/i)

  const forbiddenDatabaseData = databaseRows(`
    SELECT
      SUM(CASE WHEN role = 'system' THEN 1 ELSE 0 END),
      SUM(CASE WHEN lower(content) LIKE '%/no_think%' THEN 1 ELSE 0 END),
      SUM(CASE WHEN lower(content) LIKE '%<think%' THEN 1 ELSE 0 END),
      SUM(CASE WHEN lower(content) LIKE '%</think%' THEN 1 ELSE 0 END),
      SUM(CASE WHEN role = 'assistant' AND status != 'completed' THEN 1 ELSE 0 END)
    FROM messages
  `)[0].map((value) => value ?? 0)
  assert.deepEqual(forbiddenDatabaseData, [0, 0, 0, 0, 0])

  const allEvents = [...page.events, ...(secondPage?.events ?? [])]
  const exceptions = allEvents.filter((event) => event.method === 'Runtime.exceptionThrown')
  const logErrors = allEvents.filter(
    (event) => event.method === 'Log.entryAdded' && event.params.entry.level === 'error',
  )
  const explainedLogErrors = logErrors.filter((event) => {
    const { text, url = '' } = event.params.entry
    const missingFavicon =
      url === `${appUrl}/favicon.ico` && text.includes('404 (Not Found)')
    const intentionalBackendFailure =
      url.startsWith('http://127.0.0.1:8000/api/conversations') &&
      (text.includes('409 (Conflict)') || text.includes('ERR_CONNECTION_REFUSED'))
    return missingFavicon || intentionalBackendFailure
  })
  const unexplainedLogErrors = logErrors.filter(
    (event) => !explainedLogErrors.includes(event),
  )
  assert.deepEqual(exceptions, [], 'Aucune exception JavaScript non gérée n’est attendue.')
  assert.deepEqual(
    unexplainedLogErrors,
    [],
    'Aucune erreur de console Edge non expliquée n’est attendue.',
  )

  const requests = allEvents
    .filter((event) => event.method === 'Network.requestWillBeSent')
    .map((event) => event.params.request)
  const sendRequests = requests.filter((request) =>
    request.method === 'POST' && request.url.endsWith('/api/conversations/messages'),
  )
  assert.ok(sendRequests.length >= 3)
  for (const request of sendRequests) {
    const payload = JSON.parse(request.postData)
    assert.deepEqual(
      Object.keys(payload).sort(),
      ['conversation_id', 'expected_revision', 'message'],
    )
    assert.equal(JSON.stringify(payload).includes('/no_think'), false)
    assert.equal('history' in payload, false)
    assert.equal('role' in payload, false)
  }
  const unexpectedHttpErrors = allEvents
    .filter(
      (event) =>
        event.method === 'Network.responseReceived' &&
        event.params.response.status >= 400 &&
        event.params.response.status !== 409 &&
        event.params.response.url !== `${appUrl}/favicon.ico`,
    )
    .map((event) => ({
      status: event.params.response.status,
      url: event.params.response.url,
    }))
  assert.deepEqual(unexpectedHttpErrors, [])

  console.log(
    JSON.stringify(
      {
        verdict: 'EDGE_STAGE_8_OK',
        browserTabs: 2,
        conversationId,
        sendPayloadsChecked: sendRequests.length,
        expected409Responses: allEvents.filter(
          (event) =>
            event.method === 'Network.responseReceived' &&
            event.params.response.status === 409,
        ).length,
        runtimeExceptions: exceptions.length,
        explainedConsoleErrors: explainedLogErrors.length,
        unexplainedConsoleErrors: unexplainedLogErrors.length,
        unexpectedHttpErrors: unexpectedHttpErrors.length,
        storage,
      },
      null,
      2,
    ),
  )
} finally {
  secondPage?.close()
  page.close()
}

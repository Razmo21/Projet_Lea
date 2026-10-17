import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appUrl = 'http://127.0.0.1:5173'
const cdpPort = Number(process.env.LEA_EDGE_CDP_PORT ?? '9232')

// Pause courte entre les observations DOM, sans bloquer les autres opérations de Léa.
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))

class BrowserSession {
  // Cette connexion appartient au navigateur de test isolé, jamais au profil quotidien.
  constructor(socket) {
    this.socket = socket
    this.nextId = 0
    this.pending = new Map()
    socket.addEventListener('message', (event) => {
      const result = JSON.parse(String(event.data))
      const pending = this.pending.get(result.id)
      if (!pending) return
      this.pending.delete(result.id)
      clearTimeout(pending.timer)
      if (result.error) pending.reject(new Error(result.error.message))
      else pending.resolve(result.result)
    })
  }

  // Toutes les commandes CDP possèdent un délai et une réponse corrélée.
  send(method, params = {}) {
    const id = ++this.nextId
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error(`Délai CDP : ${method}`))
      }, 20_000)
      this.pending.set(id, { resolve, reject, timer })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  // Retourne une valeur DOM sans recopier les journaux ou raisonnements du modèle.
  async evaluate(expression) {
    const result = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
    return result.result.value
  }

  // Attend la nouvelle page, pas un sélecteur encore présent dans l'ancien DOM.
  async navigate(url = null) {
    let listener
    let timer
    const loaded = new Promise((resolve, reject) => {
      listener = (event) => {
        if (JSON.parse(String(event.data)).method === 'Page.loadEventFired') resolve()
      }
      this.socket.addEventListener('message', listener)
      timer = setTimeout(() => reject(new Error('Chargement Edge non confirmé')), 20_000)
    })
    try {
      await Promise.all([loaded, this.send(url ? 'Page.navigate' : 'Page.reload', url ? { url } : {})])
    } finally {
      clearTimeout(timer)
      this.socket.removeEventListener('message', listener)
    }
  }

  // Attend un état observable plutôt qu'un délai supposé de rendu React.
  async wait(expression, timeout = 20_000) {
    const deadline = Date.now() + timeout
    while (Date.now() < deadline) {
      if (await this.evaluate(expression)) return
      await delay(100)
    }
    throw new Error(`État DOM absent : ${expression}`)
  }

  // Produit de véritables événements souris dans Edge sur un contrôle visible.
  async click(selector, text = null) {
    const point = await this.evaluate(`(() => {
      const element = [...document.querySelectorAll(${JSON.stringify(selector)})].find(item =>
        item.getClientRects().length && !item.disabled && (${JSON.stringify(text)} === null || item.textContent.trim() === ${JSON.stringify(text)}));
      if (!element) return null;
      element.scrollIntoView({block:'center'});
      const rect = element.getBoundingClientRect();
      return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
    })()`)
    assert.ok(point, `Contrôle absent : ${selector} ${text}`)
    for (const type of ['mousePressed', 'mouseReleased']) {
      await this.send('Input.dispatchMouseEvent', { type, ...point, button: 'left', clickCount: 1 })
    }
    // La navigation React rend le focus au titre au prochain frame. Attendre
    // ce déplacement évite un clic calculé avant un défilement encore différé.
    await this.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))')
  }
}

// Les essais n'utilisent que le serveur CDP loopback explicitement lancé pour cette étape.
export async function connect() {
  const response = await fetch(`http://127.0.0.1:${cdpPort}/json/list`)
  const target = (await response.json()).find((item) => item.type === 'page')
  assert.ok(target)
  const socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true })
    socket.addEventListener('error', reject, { once: true })
  })
  const session = new BrowserSession(socket)
  await session.send('Runtime.enable')
  await session.send('Page.enable')
  await session.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false })
  return session
}

// Vérifie la vraie persistance UI, sans FastAPI ni modèle pour cette phase.
export async function settings(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('#page-title') !== null`)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="low"]')?.checked === true`)
  await session.click('input[value="high"]')
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings [role="status"]')?.textContent.includes('enregistrés')`)
  await session.navigate()
  await session.wait(`document.querySelector('#page-title') !== null`)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="high"]')?.checked === true`)
  await session.click('input[value="low"]')
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings [role="status"]')?.textContent.includes('enregistrés')`)
  await session.click('button', 'Retour aux conversations')
  assert.equal(await session.evaluate(`document.querySelector('#settings-title') === null && !document.querySelector('.chat').hidden`), true)
  console.log('PASS Edge : ouverture, Low/High sauvegardés, rechargement, retour aux conversations.')
}

// Saisit par événements navigateur, pour conserver le vrai chemin React des formulaires.
export async function type(session, selector, text) {
  await session.click(selector)
  await session.send('Input.insertText', { text })
}

// La sauvegarde UI ne démarre aucun processus et prend effet à la requête suivante.
async function choose(session, level) {
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="${level}"]') !== null`)
  if (!await session.evaluate(`document.querySelector('input[value="${level}"]').checked`)) {
    await session.click(`input[value="${level}"]`)
    await session.click('button', 'Valider')
    await session.wait(`document.querySelector('.settings [role="status"]')?.textContent.includes('enregistrés')`)
  }
  await session.click('button', 'Retour aux conversations')
}

// Exécute deux réponses réelles et vérifie le DOM public sans exposer de raisonnement brut.
export async function general(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('#question')?.disabled === false`)
  await choose(session, 'low')
  const question = 'Un article coûte 80 euros avant une remise de 25 %. Quel est son prix final ? Réponds brièvement en français.'
  await type(session, '#question', question)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="low"]')?.checked === true`)
  await session.click('button', 'Retour aux conversations')
  assert.equal(await session.evaluate(`document.querySelector('#question').value`), question)
  await session.click('button', 'Envoyer')
  await session.wait(`document.querySelector('.message-assistant') !== null && document.querySelector('#question')?.disabled === false`, 120_000)
  assert.match(await session.evaluate(`document.querySelector('.message-assistant').textContent`), /60/)
  await choose(session, 'high')
  await type(session, '#question', question)
  await session.click('button', 'Envoyer')
  await session.wait(`document.querySelectorAll('.message-assistant').length === 2 && document.querySelector('#question')?.disabled === false`, 120_000)
  const answer = await session.evaluate(`document.querySelector('.conversation-list').textContent`)
  assert.match(answer, /60/)
  assert.doesNotMatch(answer, /<\/?think>|\/(?:no_)?think|\[think\]/i)
  await type(session, '#question', 'Retiens que le code de validation étape douze est AZUR12.')
  await session.click('button', 'Envoyer')
  await session.wait(`document.querySelectorAll('.message-assistant').length === 3 && document.querySelector('#question')?.disabled === false`)
  assert.match(await session.evaluate(`document.querySelector('.conversation-list').textContent`), /retenu/)
  console.log('PASS Edge réel : brouillon conservé, réponses Général Low/High, filtrage public, mémoire explicite.')
}

// Se lance après un arrêt complet puis redémarrage des services sur la même base isolée.
export async function persistence(session) {
  await session.navigate()
  await session.wait(`document.querySelector('#question')?.disabled === false`)
  await session.wait(`document.querySelector('.conversation-list')?.textContent.includes('AZUR12')`)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="high"]')?.checked === true`)
  await session.click('button', 'Retour aux conversations')
  await type(session, '#question', 'Quel est le code de validation étape douze que je t’ai demandé de retenir ?')
  await session.click('button', 'Envoyer')
  await session.wait(`document.querySelectorAll('.message-assistant').length === 4 && document.querySelector('#question')?.disabled === false`, 120_000)
  assert.match(await session.evaluate(`[...document.querySelectorAll('.message-assistant')].at(-1).textContent`), /AZUR12/)
  console.log('PASS Edge réel : High, historique et souvenir conservés après redémarrage complet.')
}

// Un conflit réel entre deux écritures ne doit jamais devenir un message de succès.
async function errors(session) {
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="high"]')?.checked === true`)
  await session.click('input[value="low"]')
  const preference = await (await fetch(`${appUrl}/api/preferences`)).json()
  const competing = await fetch(`${appUrl}/api/preferences`, {
    method: 'POST', headers: { Origin: appUrl, 'Content-Type': 'application/json' },
    body: JSON.stringify({ expected_revision: preference.revision, general_reasoning: 'low' }),
  })
  assert.equal(competing.status, 200)
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings [role="alert"]')?.textContent.includes('autre onglet')`)
  assert.equal(await session.evaluate(`document.querySelector('.settings .status-ready') === null`), true)
  await session.click('button', 'Recharger les paramètres')
  await session.wait(`document.querySelector('input[value="low"]')?.checked === true && document.querySelector('.settings [role="alert"]') === null`)
  await session.click('button', 'Retour aux conversations')
  // Panne de transport simulée dans Edge, distincte des refus réels SQLite/HTTP.
  await session.send('Network.enable')
  await session.send('Network.setBlockedURLs', { urls: ['*api/preferences*'] })
  try {
    await session.click('button', 'Paramètres')
    await session.wait(`document.querySelector('.settings [role="alert"]')?.textContent.includes('indisponible')`)
    assert.equal(await session.evaluate(`document.querySelector('.settings input') === null`), true)
  } finally {
    await session.send('Network.setBlockedURLs', { urls: [] })
  }
  await session.click('button', 'Recharger les paramètres')
  await session.wait(`document.querySelector('input[value="low"]')?.checked === true`)
  await session.click('input[value="high"]')
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings [role="status"]')?.textContent.includes('enregistrés')`)
  await session.click('button', 'Retour aux conversations')
  console.log('PASS Edge : conflit réel visible, relecture et nouvelle sauvegarde ; panne réseau simulée sans faux succès.')
}

// Exerce le vrai moteur uniquement sur le projet jetable créé explicitement pour cette étape.
async function programming(session) {
  await session.send('Page.reload')
  await session.wait(`document.querySelector('#active-project') !== null`, 30_000)
  const projects = await (await fetch('http://127.0.0.1:8000/api/projects')).json()
  const project = projects.projects.find((item) => item.relative_path === 'Lea_Stage12_20261016')
  assert.ok(project, 'Le projet de test autorisé doit déjà exister')
  await session.evaluate(`(() => {
    const select = document.querySelector('#active-project');
    select.value = ${JSON.stringify(project.id)};
    select.dispatchEvent(new Event('change', {bubbles:true}));
  })()`)
  await session.wait(`document.querySelector('#agent-task')?.disabled === false`)
  await type(session, '#agent-task', 'Lis README.md, calculator.py et test_calculator.py. Corrige uniquement calculator.py pour que add additionne ses deux arguments. Ne modifie aucun test. Lance python -B -m unittest -v et termine après le test réussi.')
  await session.click('button', 'Lancer le run')
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('running')`, 120_000)
  const runs = await (await fetch('http://127.0.0.1:8000/api/agent-runs')).json()
  const run = runs.runs.find((item) => item.project_id === project.id && item.state === 'running')
  assert.ok(run)
  console.log(`Run réel démarré : ${run.run_id}`)
  await choose(session, 'low')
  const during = await (await fetch(`http://127.0.0.1:8000/api/agent-runs/${run.run_id}`)).json()
  assert.ok(['running', 'completed'].includes(during.state), `Run perturbé : ${during.state}`)
  assert.equal(during.model_id, run.model_id)
  console.log('PASS préférence sauvegardée pendant le run, modèle figé inchangé.')
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('completed') || document.querySelector('.agent-run-status')?.textContent.includes('failed')`, 600_000)
  const finished = await (await fetch(`http://127.0.0.1:8000/api/agent-runs/${run.run_id}`)).json()
  console.log(JSON.stringify({ run_id: run.run_id, state: finished.state, validation_status: finished.validation_status, result_summary: finished.result_summary }))
  assert.equal(finished.state, 'completed')
  assert.equal(finished.validation_status, 'validated')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('calculator.py')`)
  const changes = await (await fetch(`http://127.0.0.1:8000/api/agent-runs/${run.run_id}/changes`)).json()
  assert.deepEqual(changes.changes.map((item) => item.relative_path), ['calculator.py'])
  assert.equal(await session.evaluate(`[...document.querySelectorAll('button')].some(item => item.textContent.trim() === 'Accepter les changements' && !item.disabled)`), true)
  // La restauration demande une confirmation explicite, acceptée seulement dans ce projet de test.
  session.socket.addEventListener('message', (event) => {
    if (JSON.parse(String(event.data)).method === 'Page.javascriptDialogOpening') {
      void session.send('Page.handleJavaScriptDialog', { accept: true })
    }
  })
  await session.click('button', 'Restaurer le checkpoint')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('rolled_back')`)
  await choose(session, 'high')
  console.log('PASS Edge OpenHands réel : lecture, mutation source, test vert, validation, diff et rollback.')
}

// Compare le mécanisme réellement servi, sans enregistrer ni afficher son contenu privé.
async function native() {
  const catalog = await (await fetch('http://127.0.0.1:8080/v1/models')).json()
  for (const directive of ['/no_think', '/think']) {
    const response = await fetch('http://127.0.0.1:8080/v1/chat/completions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: catalog.data[0].id, temperature: 0, max_tokens: 1024, messages: [
        { role: 'user', content: `Un article coûte 80 euros avant une remise de 25 %. Quel est son prix final ? Réponds brièvement en français.\n${directive}` },
      ] }),
    })
    assert.equal(response.status, 200)
    const result = await response.json()
    const content = result.choices[0].message.content
    const reasoning = content.match(/<think>([\s\S]*?)<\/think>/)?.[1]?.trim() ?? ''
    assert.equal(reasoning.length > 0, directive === '/think')
    assert.match(content.replace(/<think>[\s\S]*?<\/think>/g, ''), /60/)
    console.log(JSON.stringify({ directive, private_block_nonempty: reasoning.length > 0, completion_tokens: result.usage.completion_tokens, correct_answer: true }))
  }
}

// Vérifie les vrais refus HTTP du contrôleur local, sans commande ni écriture invalide.
export async function security() {
  const before = await (await fetch(`${appUrl}/api/preferences`)).json()
  for (const [body, headers, expected] of [
    ['{}', { Origin: 'https://remote.invalid' }, 403],
    ['{}', { Origin: '' }, 403],
    ['{}', { 'Content-Type': 'text/plain' }, 415],
    ['{', {}, 422],
    ['x'.repeat(1025), {}, 422],
    [JSON.stringify({ expected_revision: before.revision, general_reasoning: 'ultra' }), {}, 422],
    [JSON.stringify({ expected_revision: before.revision, general_reasoning: 'low', path: 'C:/Windows', command: 'whoami' }), {}, 422],
  ]) {
    const result = await fetch(`${appUrl}/api/preferences`, {
      method: 'POST', headers: { Origin: appUrl, 'Content-Type': 'application/json', ...headers }, body,
    })
    assert.equal(result.status, expected)
  }
  assert.deepEqual(await (await fetch(`${appUrl}/api/preferences`)).json(), before)
  console.log('PASS HTTP réel : origines, format, taille, valeurs libres, chemins et commandes refusés sans mutation.')
}

// Produit une capture de contrôle dans le seul répertoire de test ignoré par Git.
async function visual(session) {
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('input[value="high"]')?.checked === true`)
  const capture = await session.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  await writeFile('.test-runtime/stage12-20261016/settings.png', Buffer.from(capture.data, 'base64'))
  assert.equal(await session.evaluate(`document.querySelectorAll('.settings input[type="radio"]').length`), 2)
  assert.equal(await session.evaluate(`document.activeElement.id`), 'settings-title')
  await session.click('button', 'Retour aux conversations')
  console.log('PASS capture et focus clavier de la page Paramètres.')
}

// Réutilise le client CDP dans les essais suivants, sans exécuter une phase à l'import.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const session = await connect()
  try {
    const phases = { settings, general, persistence, errors, programming, native, security, visual }
    const phase = phases[process.argv[2] ?? 'settings']
    assert.ok(phase, 'Phase inconnue')
    await phase(session)
  } finally {
    session.socket.close()
  }
}

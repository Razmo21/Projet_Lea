import assert from 'node:assert/strict'
import { readFile, readdir, writeFile } from 'node:fs/promises'
import { connect, general, persistence as checkPersistence, security, settings, type } from './edge-stage12.mjs'

const api = 'http://127.0.0.1:8000'
const appUrl = 'http://127.0.0.1:5173'

// Valide le complément sur une base fraîche : vrais modèles, mêmes mesures et styles.
async function allProfiles(session) {
  assert.equal((await (await fetch(`${appUrl}/api/preferences`)).json()).show_resource_chart, false)
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('#question')?.disabled === false`)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('.resource-option input') !== null`)
  await session.click('.resource-option input')
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings .status-ready') !== null`)
  await session.click('button', 'Retour aux conversations')

  // Les trois encadrés réutilisent exactement les mêmes propriétés visuelles.
  for (const width of [1280, 390]) {
    await session.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: false })
    const layout = await session.evaluate(`(() => {
      const form = document.querySelector('#question').closest('form');
      const style = element => {
        const value = getComputedStyle(element);
        return [value.backgroundColor, value.border, value.borderRadius, value.padding];
      };
      const textarea = document.querySelector('#question');
      return {
        styles: [form, document.querySelector('.conversation-browser'), document.querySelector('section.conversation')].map(style),
        rows: textarea.rows, height: textarea.getBoundingClientRect().height,
        containsControls: Boolean(form.querySelector('label[for="question"]') && form.querySelector('button[type="submit"]')),
        overflow: document.documentElement.scrollWidth > innerWidth,
      };
    })()`)
    assert.deepEqual(layout.styles[0], layout.styles[1])
    assert.deepEqual(layout.styles[0], layout.styles[2])
    assert.equal(layout.rows, 5)
    assert.ok(layout.height >= 100 && layout.containsControls)
    assert.equal(layout.overflow, false)
    await writeFile(`.test-runtime/stage13-all-profiles-20261017/question-${width}.png`, Buffer.from((await session.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })).data, 'base64'))
  }
  await session.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false })

  // Vérifie l'envoi depuis le formulaire encadré, pas seulement sa structure DOM.
  await type(session, '#question', 'Combien font 2 + 2 ? Réponds uniquement par le nombre.')
  await session.click('button', 'Envoyer')
  await session.wait(`document.querySelector('.message-assistant') !== null && document.querySelector('#question')?.disabled === false`, 120_000)
  assert.match(await session.evaluate(`document.querySelector('.message-assistant').textContent`), /4/)

  for (const profileId of ['general', 'development', 'general']) {
    if ((await (await fetch(`${api}/api/models/status`)).json()).active_profile_id !== profileId) {
      const switched = await fetch(`${api}/api/models/${profileId}/activate`, { method: 'POST' })
      assert.equal(switched.status, 200)
    }
    await session.wait(`document.querySelector('#model-profile')?.value === ${JSON.stringify(profileId)}`, 120_000)
    // Attend le vrai premier intervalle CPU et le snapshot du nouveau profil.
    const deadline = Date.now() + 40_000
    let readings
    do {
      readings = await (await fetch(`${api}/api/resources`)).json()
      if (readings.profile_id === profileId && !readings.stale && readings.cpu_percent != null && !readings.services.loading) break
      await new Promise((resolve) => setTimeout(resolve, 500))
    } while (Date.now() < deadline)
    assert.equal(readings.profile_id, profileId)
    assert.equal(readings.active, true)
    assert.equal(readings.stale, false)
    assert.ok(readings.ram.total_bytes > 0 && readings.vram.total_bytes > 0)
    assert.ok(typeof readings.cpu_percent === 'number' && readings.cpu_percent >= 0 && readings.cpu_percent <= 100)
    assert.equal(readings.services.model_available, true)
    assert.equal(readings.services.openhands_required, profileId === 'development')
    assert.equal(readings.services.docker_available, profileId === 'development' ? true : null)
    await session.wait(`document.querySelectorAll('.resource-chart progress').length === 3`, 20_000)
    console.log(`PASS ressources réelles ${profileId}, modèle prêt, contrôles Docker adaptés.`)
  }
  await session.navigate()
  await session.wait(`document.querySelectorAll('.resource-chart progress').length === 3`, 30_000)
  assert.equal((await (await fetch(`${appUrl}/api/preferences`)).json()).show_resource_chart, true)
  console.log('PASS encadrés identiques à 1280/390 px, saisie/envoi réel, commutations, diagramme persistant.')
}

// À exécuter après stop-core : le frontend seul ne doit plus lire les ressources.
async function stoppedResources(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('.resource-chart')?.textContent.includes('Léa est arrêtée')`)
  await session.evaluate(`(() => {
    const original = window.fetch;
    window.__resourceReads = 0;
    window.fetch = (...args) => {
      if (String(args[0]).endsWith('/api/resources')) window.__resourceReads += 1;
      return original(...args);
    };
  })()`)
  await new Promise((resolve) => setTimeout(resolve, 12_000))
  assert.equal(await session.evaluate('window.__resourceReads'), 0)
  assert.equal(await session.evaluate(`document.querySelectorAll('.resource-chart progress').length`), 0)
  await session.navigate(appUrl)
  console.log('PASS cœur arrêté : zéro lecture des ressources pendant 12 s, aucune fausse mesure.')
}

// Simule uniquement l'état lu d'un run pour vérifier la cadence React sans lancer d'agent.
async function polling(session) {
  const { identifier } = await session.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    const originalFetch = window.fetch;
    window.__runPolls = 0;
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      const url = new URL(String(args[0]), location.href);
      if (!response.ok || (args[1]?.method && args[1].method !== 'GET')) return response;
      if (url.pathname === '/api/agent-runs') {
        const body = await response.json();
        body.runs[0].state = 'running';
        return Response.json(body);
      }
      if (/^\\/api\\/agent-runs\\/[^/]+$/.test(url.pathname)) {
        window.__runPolls += 1;
        return Response.json({...await response.json(), state:'running'});
      }
      return response;
    };
  ` })
  try {
    await session.navigate(appUrl)
    await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('running')`)
    const before = await session.evaluate('window.__runPolls')
    await new Promise((resolve) => setTimeout(resolve, 12_000))
    const requests = await session.evaluate('window.__runPolls') - before
    assert.ok(requests >= 5 && requests <= 10, `Cadence anormale : ${requests} lectures / 12 s`)
    console.log(`PASS polling React borné : ${requests} lectures en 12 s (état actif simulé, aucun run lancé).`)
  } finally {
    await session.send('Page.removeScriptToEvaluateOnNewDocument', { identifier })
    await session.navigate(appUrl)
  }
}

// Vérifie la récupération durable et restaure uniquement la fixture de panne.
async function recovered(session) {
  const { runs } = await (await fetch(`${api}/api/agent-runs`)).json()
  const run = runs[0]
  assert.equal(run.state, 'failed')
  assert.equal(run.validation_status, 'failed')
  assert.match(run.failure_detail, /interrompu.*redémarrage/)
  const accept = await fetch(`${api}/api/agent-runs/${run.run_id}/accept`, { method: 'POST' })
  assert.equal(accept.status, 409)
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('failed')`)
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('calculator.py')`)
  assert.match(await session.evaluate(`document.querySelector('.agent-run-status').textContent`), /La validation du run a échoué/)
  await session.click('button', 'Restaurer le checkpoint')
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('rolled_back')`)
  const project = 'L:/IA_WORKSPACE/Lea_Stage13_20261017'
  for (const name of ['README.md', 'calculator.py', 'test_calculator.py']) {
    assert.deepEqual(await readFile(`${project}/${name}`), await readFile(`tools/openhands/fixtures/stage10-python/${name}`))
  }
  assert.deepEqual((await readdir(project)).sort(), ['README.md', 'calculator.py', 'test_calculator.py'].sort())
  assert.equal((await (await fetch(`${api}/api/agent-runs`)).json()).runs.length, 2)
  console.log('PASS interruption réelle, failed/validation échouée en UI, Accept refusé, Rollback UI exact des trois fichiers, aucun artefact ni double run.')
}

// Rouvre explicitement la conversation de test après le scénario hors IA.
async function persistence(session) {
  const { conversations } = await (await fetch(`${api}/api/conversations`)).json()
  assert.equal(conversations.length, 1)
  await session.navigate(`${appUrl}/?conversation=${conversations[0].id}`)
  await checkPersistence(session)
  assert.equal((await (await fetch(`${appUrl}/api/preferences`)).json()).show_resource_chart, true)
}

// Le contrôleur de préférences reste utilisable sans modèle ni FastAPI.
async function offline(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('#page-title') !== null`)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('.resource-option input')?.checked === true`)
  for (const checked of [false, true]) {
    await session.click('.resource-option input')
    await session.click('button', 'Valider')
    await session.wait(`document.querySelector('.settings .status-ready') !== null`)
    assert.equal((await (await fetch(`${appUrl}/api/preferences`)).json()).show_resource_chart, checked)
  }
  await session.click('button', 'Retour aux conversations')
  console.log('PASS paramètre du diagramme enregistré avec le cœur arrêté.')
}

// Vérifie les préférences réelles, pas un état de formulaire seulement simulé.
async function chart(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('#page-title') !== null`)
  const initial = await (await fetch(`${appUrl}/api/preferences`)).json()
  assert.equal(initial.show_resource_chart, false)
  assert.equal(await session.evaluate(`document.querySelector('.resource-chart') === null`), true)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('.resource-option input') !== null`)
  await session.click('.resource-option input')
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings .status-ready') !== null`)
  await session.click('button', 'Retour aux conversations')
  await session.wait(`document.querySelector('.resource-chart') !== null`)
  await session.navigate()
  await session.wait(`document.querySelector('.resource-chart') !== null`)
  assert.equal((await (await fetch(`${appUrl}/api/preferences`)).json()).show_resource_chart, true)
  console.log('PASS diagramme masqué par défaut, activation UI, commit et rechargement.')
}

// Exerce le chemin utilisateur complet sur le seul projet jetable préparé pour cet essai.
async function programming(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('#active-project') !== null`, 30_000)
  const { projects } = await (await fetch(`${api}/api/projects`)).json()
  const project = projects.find((item) => item.relative_path === 'Lea_Stage13_20261017')
  assert.ok(project)
  await session.evaluate(`(() => {
    const select = document.querySelector('#active-project');
    select.value = ${JSON.stringify(project.id)};
    select.dispatchEvent(new Event('change', {bubbles:true}));
  })()`)
  await session.wait(`document.querySelector('#agent-task')?.disabled === false`)
  await type(session, '#agent-task', 'Lis README.md, calculator.py et test_calculator.py. Corrige uniquement calculator.py pour que add additionne ses deux arguments. Ne modifie aucun test. Lance python -B -m unittest -v et termine après le test réussi.')
  await session.click('button', 'Lancer le run')
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('running')`, 120_000)
  await finish(session)
}

// Le diff est chargé automatiquement après le verdict, sans contrôle UI fictif.
async function finish(session) {
  await session.wait(`document.querySelector('.agent-run-status')?.textContent.includes('Validation réelle confirmée')`, 360_000)
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('calculator.py')`)
  const buttons = await session.evaluate(`[...document.querySelectorAll('.agent-changes button')].map(item=>item.textContent.trim())`)
  const accept = buttons.find((text) => /accepter/i.test(text))
  assert.ok(accept)
  await session.click('button', accept)
  await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('accepted')`)
  console.log('PASS run OpenHands réel, lecture, correction source, test vert, diff et Accept.')
}

// La pression est simulée dans le navigateur, sans épuiser réellement la machine.
async function alerts(session) {
  await session.navigate(appUrl)
  await session.wait(`document.querySelector('.resource-chart progress') !== null`, 40_000)
  const readings = await (await fetch(`${api}/api/resources`)).json()
  assert.equal(readings.active, true)
  assert.equal(readings.stale, false)
  assert.ok(readings.ram.total_bytes > readings.ram.used_bytes)
  assert.ok(readings.cpu_percent >= 0 && readings.cpu_percent <= 100)
  assert.ok(readings.vram?.total_bytes > 0)
  console.log(JSON.stringify({ ram: readings.ram, cpu: readings.cpu_percent, vram: readings.vram, collection_ms: readings.collection_ms }))
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('.resource-option input')?.checked === true`)
  await session.click('.resource-option input')
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings .status-ready') !== null`)
  await session.click('button', 'Retour aux conversations')
  await session.wait(`document.querySelector('.resource-chart') === null`)
  await session.evaluate(`(() => {
    const original = window.fetch;
    window.__stage13Fetch = original;
    window.fetch = (...args) => String(args[0]).endsWith('/api/resources')
      ? Promise.resolve(Response.json(${JSON.stringify({ ...readings, level: 'CRITICAL', messages: ['Alerte critique simulée pour le test UI.'], ram: null, vram: null, cpu_percent: null })}))
      : original(...args);
  })()`)
  try {
    await session.wait(`document.querySelector('.resources [role="alert"]')?.textContent.includes('critique simulée')`, 20_000)
    assert.equal(await session.evaluate(`document.querySelector('.resource-chart') === null`), true)
    assert.equal((await (await fetch(`${api}/api/models/status`)).json()).active_profile_id, 'development')
    await writeFile('.test-runtime/stage13-20261017/alert-hidden-chart.png', Buffer.from((await session.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })).data, 'base64'))
  } finally {
    await session.evaluate(`window.fetch = window.__stage13Fetch; delete window.__stage13Fetch`)
  }
  console.log('PASS vraies mesures, désactivation du diagramme, alerte critique simulée toujours visible ; aucun arrêt de service.')
}

const session = await connect()
try {
  const phase = { settings, general, persistence, security, chart, programming, finish, alerts, offline, recovered, polling, allProfiles, stoppedResources }[process.argv[2]]
  assert.ok(phase, 'Phase inconnue')
  await phase(session)
} finally {
  session.socket.close()
}

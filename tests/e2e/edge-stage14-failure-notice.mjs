import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { connect } from './edge-stage12.mjs'

const app = 'http://127.0.0.1:5173'
const api = 'http://127.0.0.1:8000'
const failed = JSON.parse(await readFile('.test-runtime/stage14-20261017/browser-programming-feedback.json', 'utf8')).run
assert.equal(failed.state, 'failed')
const session = await connect()
const original = await (await fetch(`${app}/api/preferences`)).json()
const before = await (await fetch(`${api}/api/agent-runs`)).json()

// Test-only replay of a known failed result: never create or repeat a project run.
async function preference(enabled) {
  const current = await (await fetch(`${app}/api/preferences`)).json()
  const response = await fetch(`${app}/api/preferences`, {
    method: 'POST', headers: {Origin: app, 'Content-Type': 'application/json'},
    body: JSON.stringify({expected_revision: current.revision, voice_enabled: enabled}),
  })
  assert.equal(response.status, 200)
}

try {
  for (const enabled of [false, true]) {
    await preference(enabled)
    await session.navigate(app)
    await session.wait(`document.body.innerText.includes('Programmation est prêt.')`, 30000)
    await session.wait(`document.querySelector('.agent-changes')?.textContent.includes('accepted') && [...document.querySelectorAll('button')].some(b=>b.textContent==='Conversation vocale' && !b.disabled)`, 30000)
    await session.evaluate(`(() => {
      window.__spoken = 0; const original = window.fetch;
      window.fetch = (...args) => {
        if (String(args[0]).endsWith('/api/agent-runs') && args[1]?.method === 'POST') return Promise.resolve(new Response(JSON.stringify(${JSON.stringify(failed)}), {status:202}));
        if (String(args[0]).endsWith('/api/voice/speak')) {window.__spoken++; return Promise.resolve(new Response(JSON.stringify({detail:'Synthèse indisponible (test)'}), {status:503}));}
        return original(...args);
      };
    })()`)
    await session.click('button', 'Conversation vocale')
    await session.wait(`!![...document.querySelectorAll('button')].find(b=>b.textContent==='Parler à Léa' && !b.disabled && b.getClientRects().length)`)
    await session.click('button', 'Parler à Léa')
    await session.wait(`document.body.innerText.includes('Clique à nouveau pour terminer')`)
    await new Promise(resolve => setTimeout(resolve, 6500))
    await session.click('button', 'Terminer et envoyer')
    await session.wait(`document.body.innerText.includes('Run OpenHands : failed. Validation : failed.')`, 30000)
    await session.wait(`document.body.innerText.includes('${enabled ? 'Synthèse indisponible (test)' : 'lecture désactivée'}')`, 30000)
    assert.equal(await session.evaluate('window.__spoken'), enabled ? 1 : 0)
    assert.equal(await session.evaluate(`!![...document.querySelectorAll('.message, textarea')].find(el=>el.getClientRects().length)`), false)
    await session.click('button', 'Examiner le run et le diff')
  }
  assert.deepEqual(await (await fetch(`${api}/api/agent-runs`)).json(), before)
  console.log('PASS résultat simulé : failed reste visible sans TTS ou si synthèse échoue ; aucun run créé/rejoué.')
} finally {
  await preference(original.voice_enabled)
  session.socket.close()
}

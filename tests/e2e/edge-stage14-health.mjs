import assert from 'node:assert/strict'
import { connect } from './edge-stage12.mjs'

// Only health responses are simulated; the real UI, microphone lifecycle and
// local profile remain running. No process or model state is changed by this test.
const session = await connect()
try {
  await session.navigate('http://127.0.0.1:5173')
  await session.wait(`document.querySelector('.core-status')?.textContent.includes('prête')`, 30000)
  await session.evaluate(`(() => {
    window.__probeFailures = 0; window.__probeCount = 0;
    const original = window.fetch;
    window.fetch = (...args) => {
      if (String(args[0]).endsWith('/api/core/status') && window.__probeFailures > 0) {
        window.__probeFailures--; window.__probeCount++;
        return Promise.resolve(new Response(JSON.stringify({state:'error', model:'stopped', backend:'error', message:'Sonde indisponible (test)'}), {status:200}));
      }
      return original(...args);
    };
    window.__probeFailures = 1;
  })()`)
  await session.click('button', 'Conversation vocale')
  await session.click('button', 'Parler à Léa')
  await session.wait(`document.body.innerText.includes('Clique à nouveau pour terminer')`)
  await session.wait('window.__probeCount === 1', 15000)
  assert.equal(await session.evaluate(`document.body.innerText.includes('Clique à nouveau pour terminer')`), true)
  await session.wait(`window.__probeFailures === 0 && document.querySelector('.core-status')?.textContent.includes('prête')`)
  // Three consecutive failures still invalidate audio and expose a durable error.
  await session.evaluate('window.__probeFailures = 3; window.__probeCount = 0')
  await session.wait(`window.__probeCount === 3 && document.body.innerText.includes('Contexte modifié')`, 30000)
  assert.equal(await session.evaluate(`document.querySelector('.core-status').classList.contains('status-error')`), true)
  await session.click('button', 'Retour aux conversations')
  await session.wait(`document.querySelector('.core-status')?.textContent.includes('prête')`, 20000)
  console.log('PASS sonde simulée : incident isolé toléré ; panne persistante annule l’audio ; récupération visible.')
} finally { session.socket.close() }

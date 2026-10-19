import assert from 'node:assert/strict'
import { connect } from './edge-stage12.mjs'

const app = 'http://127.0.0.1:5173'
const session = await connect()

// Exercise the real Settings component and isolated SQLite controller, without a model request.
async function chooseVoice(id) {
  await session.evaluate(`(() => { const element = document.querySelector('#voice-id'); element.value = ${JSON.stringify(id)}; element.dispatchEvent(new Event('change', {bubbles:true})); })()`)
}

try {
  await session.navigate(app)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('#voice-id')?.options.length === 2`)
  assert.deepEqual(
    await session.evaluate(`[...document.querySelector('#voice-id').options].map(option => option.textContent)`),
    ['Léa — Voix naturelle française', 'SIWIS — Voix classique'],
  )
  assert.equal(await session.evaluate(`document.querySelector('#voice-id').value`), 'lea_voice')
  assert.equal(await session.evaluate(`document.querySelector('#voice-rate').disabled`), true)

  await chooseVoice('fr-siwis')
  await session.wait(`document.querySelector('#voice-rate').disabled === false`)
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings .status-ready') !== null`)
  await session.navigate(app)
  await session.click('button', 'Paramètres')
  await session.wait(`document.querySelector('#voice-id')?.options.length === 2 && document.querySelector('#voice-id')?.value === 'fr-siwis'`)

  await chooseVoice('lea_voice')
  await session.wait(`document.querySelector('#voice-rate').disabled === true && document.body.innerText.includes('vitesse fixe à 1×')`)
  await session.click('button', 'Valider')
  await session.wait(`document.querySelector('.settings .status-ready') !== null`)
  const saved = await (await fetch(`${app}/api/preferences`)).json()
  assert.equal(saved.voice_id, 'lea_voice')
  assert.equal(saved.voice_rate, 1.2)
  console.log('PASS noms, sélection des deux moteurs, limite de vitesse et persistance SQLite dans la vraie interface.')
} finally {
  session.socket.close()
}

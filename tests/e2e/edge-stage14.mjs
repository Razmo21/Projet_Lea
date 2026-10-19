import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { connect, type } from './edge-stage12.mjs'

const app = 'http://127.0.0.1:5173'
const api = 'http://127.0.0.1:8000'
const output = '.test-runtime/stage14-20261017'
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const session = await connect()

// Observe audio lifecycle in the isolated fake-device browser, not physical speakers.
async function instrument() {
  await session.evaluate(`(() => {
    window.__voiceTracks = []; window.__voiceCalls = []; window.__voicePlayback = [];
    const media = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (...args) => {
      const stream = await media(...args); window.__voiceTracks.push(...stream.getTracks()); return stream;
    };
    const transport = window.fetch;
    window.fetch = async (...args) => {
      const url = String(args[0]); const entry = {url, start: performance.now()};
      window.__voiceCalls.push(entry);
      const result = await transport(...args); entry.end = performance.now(); entry.status = result.status; return result;
    };
    const start = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function(...args) {
      if (this.context instanceof AudioContext) window.__voicePlayback.push({time: performance.now(), state: this.context.state});
      return start.apply(this, args);
    };
  })()`)
}

// Real MediaRecorder + real Whisper, with a synthetic microphone explicitly selected at launch.
async function record(startLabel, stopLabel, milliseconds = 4000) {
  await session.click('button', startLabel)
  await session.wait(`document.body.innerText.includes('Clique à nouveau pour terminer')`)
  await pause(milliseconds)
  await session.click('button', stopLabel)
}

try {
  await session.navigate(app)
  await session.wait(`document.querySelector('#question') !== null && [...document.querySelectorAll('button')].some(b => b.textContent === 'Dicter au microphone' && !b.disabled)`, 30000)
  if (!process.argv.includes('--stopped')) await session.wait(`document.body.innerText.includes('Général est prêt.')`, 30000)
  await instrument()
  if (process.argv.includes('--stopped')) {
    await record('Dicter au microphone', 'Terminer la dictée')
    await session.wait(`document.body.innerText.includes('Dictée ajoutée au brouillon')`, 30000)
    assert.equal(await session.evaluate(`document.querySelector('#question').disabled`), false)
    assert.equal(await session.evaluate(`window.__voiceCalls.some(item => item.url.endsWith('/api/conversations/messages'))`), false)
    await session.click('button', 'Conversation vocale')
    assert.match(await session.evaluate('document.body.innerText'), /Démarre un profil IA/)
    console.log('PASS dictée réelle cœur arrêté, aucun démarrage ni envoi implicite.')
  } else {
    await type(session, '#question', 'Brouillon conservé :')
    await record('Dicter au microphone', 'Terminer la dictée')
    await type(session, '#question', 'Brouillon modifié pendant transcription :')
    await session.wait(`document.body.innerText.includes('Dictée ajoutée au brouillon')`, 30000)
    const draft = await session.evaluate(`document.querySelector('#question').value`)
    assert.match(draft, /^Brouillon conservé :/)
    assert.match(draft, /Brouillon modifié pendant transcription/)
    assert.match(draft, /Combien/i)
    assert.equal(await session.evaluate(`window.__voiceCalls.some(item => item.url.endsWith('/api/conversations/messages'))`), false)
    assert.equal(await session.evaluate(`window.__voiceCalls.some(item => item.url.endsWith('/api/voice/speak'))`), false)
    await session.click('button', 'Envoyer')
    await session.wait(`document.querySelector('.message-assistant') && !document.querySelector('#question').disabled`, 120000)
    console.log('PASS dictée réelle, brouillon préservé, édition et envoi manuel Général.')

    await session.click('button', 'Nouvelle conversation')
    await session.click('button', 'Conversation vocale')
    assert.equal(await session.evaluate(`!![...document.querySelectorAll('.message, textarea')].find(el => el.getClientRects().length)`), false)
    await record('Parler à Léa', 'Terminer et envoyer')
    await session.wait(`window.__voicePlayback.length > 0`, 120000)
    await session.wait(`document.body.innerText.includes('Prête pour une intervention')`, 20000)
    assert.equal(await session.evaluate(`window.__voiceTracks.every(track => track.readyState === 'ended')`), true)
    const first = await session.evaluate(`window.__voiceCalls.filter(item => item.url.endsWith('/api/conversations/messages')).length`)
    await session.click('button', 'Retour aux conversations')
    await session.wait(`document.querySelectorAll('.message-assistant').length === 1`)
    const id = new URL(await session.evaluate('location.href')).searchParams.get('conversation')
    const detail = await (await fetch(`${api}/api/conversations/${id}`)).json()
    assert.equal(detail.messages.length, 2)
    assert.ok(detail.messages[1].content.trim().length > 0)
    await session.navigate()
    await session.wait(`document.querySelectorAll('.message-assistant').length === 1`)
    await instrument()
    await session.click('button', 'Conversation vocale')
    await record('Parler à Léa', 'Terminer et envoyer')
    await session.wait(`document.body.innerText.includes('Léa parle')`, 120000)
    await session.click('button', 'Arrêter la lecture')
    await session.wait(`document.body.innerText.includes('Prête pour une intervention')`)
    assert.equal(await session.evaluate(`window.__voiceTracks.every(track => track.readyState === 'ended')`), true)
    await session.click('button', 'Parler à Léa')
    await session.wait(`document.body.innerText.includes('Clique à nouveau pour terminer')`)
    await session.click('button', 'Retour aux conversations')
    assert.equal(await session.evaluate(`window.__voiceTracks.every(track => track.readyState === 'ended')`), true)
    const final = await (await fetch(`${api}/api/conversations/${id}`)).json()
    assert.equal(final.messages.length, 4)
    assert.equal(first, 2)
    const timings = await session.evaluate(`({calls: window.__voiceCalls, playback: window.__voicePlayback})`)
    await writeFile(`${output}/browser-general.json`, JSON.stringify({ syntheticMicrophone: true, mutedOutput: true, timings }, null, 2))
    console.log('PASS échange vocal Général réel, lecture navigateur, interruption, recharge, 4 messages sans doublon, fermeture du micro.')
    await session.click('button', 'Paramètres')
    await session.wait(`document.querySelector('#voice-volume') !== null`)
    assert.deepEqual(
      await session.evaluate(`[...document.querySelector('#voice-id').options].map(option => option.textContent)`),
      ['Léa — Voix naturelle française', 'SIWIS — Voix classique'],
    )
    assert.equal(await session.evaluate(`document.querySelector('#voice-id').value`), 'lea_voice')
    assert.equal(await session.evaluate(`document.querySelector('#voice-rate').disabled`), true)
    await session.evaluate(`(() => { const element = document.querySelector('#voice-id'); element.value = 'fr-siwis'; element.dispatchEvent(new Event('change', {bubbles:true})); })()`)
    await session.wait(`document.querySelector('#voice-rate').disabled === false`)
    await session.evaluate(`(() => { const element = document.querySelector('#voice-rate'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, '1.2'); element.dispatchEvent(new Event('input', {bubbles:true})); element.dispatchEvent(new Event('change', {bubbles:true})); })()`)
    await session.evaluate(`(() => { const element = document.querySelector('#voice-volume'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(element, '0.5'); element.dispatchEvent(new Event('input', {bubbles:true})); element.dispatchEvent(new Event('change', {bubbles:true})); })()`)
    await session.click('button', 'Valider')
    await session.wait(`document.querySelector('.settings .status-ready') !== null`)
    const classicPreferences = await (await fetch(`${app}/api/preferences`)).json()
    assert.equal(classicPreferences.voice_volume, .5)
    assert.equal(classicPreferences.voice_id, 'fr-siwis')
    assert.equal(classicPreferences.voice_rate, 1.2)
    await session.navigate()
    await session.click('button', 'Paramètres')
    await session.wait(`document.querySelector('#voice-id')?.options.length === 2 && document.querySelector('#voice-volume')?.value === '0.5' && document.querySelector('#voice-id')?.value === 'fr-siwis'`)
    await session.evaluate(`(() => { const element = document.querySelector('#voice-id'); element.value = 'lea_voice'; element.dispatchEvent(new Event('change', {bubbles:true})); })()`)
    await session.wait(`document.querySelector('#voice-rate').disabled === true && document.body.innerText.includes('vitesse fixe à 1×')`)
    await session.click('button', 'Valider')
    await session.wait(`document.querySelector('.settings .status-ready') !== null`)
    const naturalPreferences = await (await fetch(`${app}/api/preferences`)).json()
    assert.equal(naturalPreferences.voice_id, 'lea_voice')
    assert.equal(naturalPreferences.voice_rate, 1.2)
    console.log('PASS deux moteurs sélectionnables, vitesse réelle SIWIS, limite Pocket explicite et persistance SQLite.')
  }
} finally { session.socket.close() }

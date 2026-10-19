import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const origin = 'http://127.0.0.1:5173'
const headers = { Origin: origin, 'Content-Type': 'application/json' }
const recording = await readFile('.test-runtime/stage14-20261017/synthetic-question.wav')

// Real HTTP refusals, without running commands supplied by an untrusted caller.
for (const [path, method, extra, expected] of [
  ['speak', 'POST', { Origin: 'https://outside.invalid' }, 403],
  ['speak', 'POST', { Origin: '' }, 403],
  ['speak', 'GET', {}, 405],
  ['shell', 'POST', {}, 404],
  ['speak', 'POST', { 'Content-Type': 'text/plain' }, 415],
]) {
  const response = await fetch(`${origin}/api/voice/${path}`, { method, headers: { ...headers, ...extra }, ...(method === 'POST' ? { body: '{}' } : {}) })
  assert.equal(response.status, expected)
}

// Disconnect after the worker has started, then require a newly verified free slot.
const controller = new AbortController()
const pending = fetch(`${origin}/api/voice/transcribe`, { method: 'POST', headers, signal: controller.signal,
  body: JSON.stringify({ audio: recording.toString('base64'), language: 'fr' }) }).then(() => 'completed', () => 'aborted')
await new Promise(resolve => setTimeout(resolve, 700))
controller.abort()
assert.equal(await pending, 'aborted')
let status
for (let attempt = 0; attempt < 20; attempt++) {
  await new Promise(resolve => setTimeout(resolve, 200))
  status = await fetch(`${origin}/api/voice/status`)
  if (status.status !== 409) break
}
assert.equal(status.status, 200)
assert.equal((await status.json()).stt, true)

// Abort a real Pocket TTS generation while its model is active; no resident model may keep the slot.
const speechController = new AbortController()
const speech = fetch(`${origin}/api/voice/speak`, { method: 'POST', headers, signal: speechController.signal,
  body: JSON.stringify({ text: 'Cette réponse longue vérifie que la fermeture arrête réellement le moteur vocal local. '.repeat(80), voice_id: 'lea_voice', rate: 1 }) }).then(() => 'completed', () => 'aborted')
await new Promise(resolve => setTimeout(resolve, 900))
speechController.abort()
assert.equal(await speech, 'aborted')
for (let attempt = 0; attempt < 30; attempt++) {
  await new Promise(resolve => setTimeout(resolve, 200))
  status = await fetch(`${origin}/api/voice/status`)
  if (status.status !== 409) break
}
assert.equal(status.status, 200)
assert.equal((await status.json()).voices[0].id, 'lea_voice')
console.log('PASS refus HTTP locaux réels, abandons STT/Pocket TTS et slots libérés après fermeture des workers.')

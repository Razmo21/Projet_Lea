import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { voiceController } from '../../tools/voice-controller.ts'

// Exercise HTTP policy and worker ownership without a Python engine in unit tests.
function harness(automatic = true) {
  let middleware: any
  const calls: any[] = []
  const plugin = voiceController((command, args, options) => {
    const child: any = new EventEmitter()
    child.stdout = new EventEmitter(); child.stderr = new EventEmitter(); child.stdin = new EventEmitter()
    const call = { command, args, options, child, input: '', killed: false }
    calls.push(call)
    child.kill = () => { call.killed = true; queueMicrotask(() => child.emit('close', 64)) }
    child.stdin.destroy = () => {}
    child.stdin.write = (input: string) => {
      call.input = input
      if (automatic) queueMicrotask(() => {
        child.stdout.emit('data', JSON.stringify({ status: 200, body: { text: 'Bonjour Léa' } }))
        child.emit('close', 0)
      })
    }
    return child
  })
  ;(plugin.configResolved as Function)({ root: 'L:/Projet_Lea' })
  const server = new EventEmitter()
  ;(plugin.configureServer as Function)({ httpServer: server, middlewares: { use(handler: any) { middleware = handler } } })

  // Simulate a same-origin browser; no headers are implicitly trusted by the middleware.
  function request(path = 'transcribe', body = '{}', headers: Record<string, string> = {}, method = 'POST') {
    const incoming = Object.assign(new EventEmitter(), { url: `/api/voice/${path}`, method,
      headers: { host: '127.0.0.1:5173', origin: 'http://127.0.0.1:5173', 'content-type': 'application/json', ...headers }, setEncoding() {} })
    const response: any = new EventEmitter()
    response.statusCode = 0; response.writableEnded = false; response.destroyed = false; response.setHeader = () => {}
    const result = new Promise<{ status: number; body: any }>((resolve) => {
      response.end = (value: string) => { response.writableEnded = true; resolve({ status: response.statusCode, body: JSON.parse(value) }) }
    })
    middleware(incoming, response, () => { throw new Error('Lost route') })
    incoming.emit('data', body); incoming.emit('end')
    return { result, response }
  }
  return { request, calls, server }
}

test('voice controller launches only a fixed local worker with an open ownership pipe', async () => {
  const h = harness(), body = JSON.stringify({ text: 'Léa, été', voice_id: 'fr-siwis', rate: 1 })
  assert.equal((await h.request('speak', body).result).status, 200)
  assert.deepEqual(h.calls[0].args, ['-B', 'L:/Projet_Lea/tools/voice/worker.py', 'speak'])
  assert.equal(h.calls[0].options.shell, false)
  assert.equal(h.calls[0].input, body + '\n')
})

test('voice controller rejects external origins, rebinding, wrong methods and oversized audio', async () => {
  const h = harness()
  for (const [path, body, headers, method, status] of [
    ['speak', '{}', { origin: 'https://outside.invalid' }, 'POST', 403],
    ['speak', '{}', { origin: '' }, 'POST', 403],
    ['status', '', { host: 'outside.invalid:5173' }, 'GET', 403],
    ['status', '', { 'sec-fetch-site': 'cross-site' }, 'GET', 403],
    ['speak', '{}', {}, 'GET', 405],
    ['speak', '{}', { 'content-type': 'text/plain' }, 'POST', 415],
    ['command', '{}', {}, 'POST', 404],
    ['transcribe', 'x'.repeat(5_200_001), {}, 'POST', 422],
  ] as const) assert.equal((await h.request(path, body, headers, method).result).status, status)
  assert.equal(h.calls.length, 0)
})

test('voice serialization lasts until verified child close and disconnect cancels ownership', async () => {
  const h = harness(false), first = h.request()
  await Promise.resolve(); await Promise.resolve()
  assert.equal((await h.request().result).status, 409)
  first.response.destroyed = true; first.response.emit('close')
  assert.equal(h.calls[0].killed, true)
  await Promise.resolve()
  const second = h.request()
  await Promise.resolve(); await Promise.resolve()
  assert.equal(h.calls.length, 2)
  h.server.emit('close')
  assert.equal(h.calls[1].killed, true)
  await second.result
})

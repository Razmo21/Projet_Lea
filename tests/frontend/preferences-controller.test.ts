import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import { preferencesController } from '../../tools/preferences-controller.ts'

// Injecte seulement l'enfant Python ; le middleware HTTP réel reste sous test.
function harness(reply = { status: 200, body: { revision: 0, general_reasoning: 'low' } }) {
  const calls: { command: string; args: string[]; options: unknown; input?: string }[] = []
  let middleware: (request: any, response: any, next: () => void) => void
  const plugin = preferencesController((command, args, options) => {
    const call = { command, args, options, input: '' }
    calls.push(call)
    const child = new EventEmitter() as any
    child.stdout = new EventEmitter()
    child.stderr = new EventEmitter()
    child.stdin = new EventEmitter()
    child.kill = () => true
    // Répond après stdin, comme l'utilitaire ponctuel, sans ouvrir de service.
    child.stdin.end = (input: string) => {
      call.input = input
      queueMicrotask(() => {
        child.stdout.emit('data', JSON.stringify(reply))
        child.emit('close', 0)
      })
    }
    return child
  })
  ;(plugin.configResolved as Function)({ root: 'L:/Projet_Lea' })
  ;(plugin.configureServer as Function)({ middlewares: { use: (handler: typeof middleware) => { middleware = handler } } })

  // Simule uniquement le transport HTTP avec ses en-têtes et octets réels.
  async function request(method: string, body = '', headers: Record<string, string> = {}) {
    const incoming = Object.assign(new EventEmitter(), {
      url: '/api/preferences', method,
      headers: { host: '127.0.0.1:5173', origin: 'http://127.0.0.1:5173', 'content-type': 'application/json', ...headers },
    })
    return new Promise<{ status: number; body: any }>((resolve) => {
      const response = {
        statusCode: 0,
        setHeader() {},
        // Conserve le statut HTTP réellement choisi par le contrôleur.
        end(value: string) { resolve({ status: response.statusCode, body: JSON.parse(value) }) },
      }
      middleware(incoming, response, () => { throw new Error('Route perdue') })
      incoming.emit('data', Buffer.from(body))
      incoming.emit('end')
    })
  }
  return { request, calls }
}

test('preferences use a fixed Python command without shell or model startup', async () => {
  const app = harness()
  assert.equal((await app.request('GET')).status, 200)
  await app.request('POST', '{"general_reasoning":"high","expected_revision":0}')
  assert.deepEqual(app.calls[1].args, ['-B', 'L:/Projet_Lea/tools/preferences.py', 'save'])
  assert.equal(app.calls[1].input, '{"general_reasoning":"high","expected_revision":0}')
  assert.equal((app.calls[1].options as any).shell, false)
})

test('preferences reject remote origins, host rebinding, unsupported methods and oversized bodies', async () => {
  const app = harness()
  for (const [method, body, headers, status] of [
    ['POST', '{}', { origin: 'https://remote.invalid' }, 403],
    ['GET', '', { host: 'evil.invalid:5173' }, 403],
    ['GET', '', { 'sec-fetch-site': 'cross-site' }, 403],
    ['DELETE', '', {}, 405],
    ['POST', '{}', { 'content-type': 'text/plain' }, 415],
    ['POST', 'x'.repeat(1025), {}, 422],
  ] as const) {
    assert.equal((await app.request(method, body, headers)).status, status)
  }
  assert.equal(app.calls.length, 0)
})

test('preferences preserve backend refusal instead of confirming a save', async () => {
  const app = harness({ status: 503, body: { detail: 'Stockage indisponible' } } as any)
  assert.equal((await app.request('POST', '{}')).status, 503)
})

test('preferences serialize writes and release the lock after completion', async () => {
  const app = harness()
  const first = app.request('POST', '{"general_reasoning":"high","expected_revision":0}')
  const second = app.request('POST', '{"general_reasoning":"low","expected_revision":0}')
  assert.equal((await second).status, 409)
  assert.equal((await first).status, 200)
  assert.equal((await app.request('POST', '{}')).status, 200)
  assert.equal(app.calls.length, 2)
})

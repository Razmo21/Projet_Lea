import type { Plugin } from 'vite'

type Child = any
type Spawn = (command: string, args: string[], options: unknown) => Child
const timers = globalThis as unknown as { setTimeout(fn: () => void, ms: number): any; clearTimeout(id: any): void }
const limit = 5_200_000
const byteLength = (globalThis as unknown as { Buffer: { byteLength(value: string): number } }).Buffer.byteLength

// Ce contrôleur local réutilise Vite ; aucune commande ou aucun chemin ne vient du client.
export function voiceController(spawn: Spawn): Plugin {
  let root = ''
  let active: Child | null = null
  const children = new Set<Child>()

  // La fermeture de stdin réveille le gardien du worker et arrête son job Windows.
  function cancel(child: Child) { child.stdin.destroy(); child.kill() }

  // Les sorties d'erreur privées et les données audio ne sont jamais journalisées.
  function send(response: any, status: number, body: unknown) {
    if (response.destroyed || response.writableEnded) return
    response.statusCode = status
    response.setHeader('Content-Type', 'application/json; charset=utf-8')
    response.setHeader('Cache-Control', 'no-store')
    response.setHeader('X-Content-Type-Options', 'nosniff')
    response.end(JSON.stringify(body))
  }

  // Le corps est plafonné pendant sa réception, pas après une allocation illimitée.
  function read(request: any): Promise<string> {
    return new Promise((resolve, reject) => {
      let value = ''
      let size = 0
      let settled = false
      request.setEncoding('utf8')
      const timer = timers.setTimeout(() => finish(new Error('Délai audio dépassé.')), 15_000)
      // Les chemins d'erreur libèrent tous le délai, même après un abandon réseau.
      function finish(error?: Error) {
        if (settled) return
        settled = true
        timers.clearTimeout(timer)
        if (error) reject(error); else resolve(value)
      }
      request.on('data', (chunk: any) => {
        if (settled) return
        size += byteLength(chunk)
        if (size > limit) finish(new Error('Enregistrement trop volumineux.'))
        else value += String(chunk)
      })
      request.once('end', () => finish())
      request.once('aborted', () => finish(new Error('Enregistrement interrompu.')))
      request.once('error', () => finish(new Error('Enregistrement interrompu.')))
    })
  }

  // Un worker par opération libère modèle, mémoire et enfants à sa sortie.
  async function invoke(action: string, request: any, response: any) {
    let child: Child | null = null
    let timer: any
    let ended = false
    try {
      const raw = action === 'status' ? '{}' : await read(request)
      const body = JSON.parse(raw)
      if (!body || Array.isArray(body) || typeof body !== 'object') throw new Error('Requête vocale invalide.')
      if (response.destroyed) return
      if (active || children.size >= 2) { send(response, 409, { detail: 'Un traitement vocal est déjà en cours.' }); return }
      child = spawn(`${root}/runtime/voice/.venv/Scripts/python.exe`, ['-B', `${root}/tools/voice/worker.py`, action], {
        cwd: root, shell: false, windowsHide: true,
      })
      children.add(child)
      if (action !== 'status') active = child
      let output = ''
      // Ne libère le slot qu'à close : kill demandé n'est pas un arrêt confirmé.
      const fail = () => {
        if (ended) return
        ended = true
        cancel(child)
        send(response, 503, { detail: 'Traitement vocal interrompu ou délai dépassé.' })
      }
      timer = timers.setTimeout(fail, action === 'status' ? 10_000 : 190_000)
      response.once('close', () => { if (!response.writableEnded) fail() })
      child.once('error', fail)
      child.stdin.on('error', fail)
      child.stderr.on('data', () => {})
      child.stdout.on('data', (chunk: unknown) => {
        if (ended) return
        output += String(chunk)
        if (output.length > 34 * 1024 * 1024) fail()
      })
      child.once('close', (code: number | null) => {
        timers.clearTimeout(timer)
        children.delete(child)
        if (active === child) active = null
        if (ended) return
        ended = true
        try {
          const reply = JSON.parse(output)
          if (code !== 0 || ![200, 422, 503].includes(reply.status) || !reply.body) throw new Error()
          send(response, reply.status, reply.body)
        } catch { send(response, 503, { detail: 'Le moteur vocal local n’a pas confirmé son résultat.' }) }
      })
      // Ne ferme pas stdin : son EOF signifie exclusivement annulation ou mort de Vite.
      child.stdin.write(`${JSON.stringify(body)}\n`)
    } catch {
      if (child) cancel(child)
      send(response, 422, { detail: 'Requête vocale invalide, trop grande ou interrompue.' })
    }
  }

  return {
    name: 'lea-voice-controller', apply: 'serve',
    configResolved(config) { root = config.root },
    configureServer(server) {
      server.httpServer?.once('close', () => { for (const child of children) cancel(child) })
      server.middlewares.use((request: any, response: any, next: any) => {
        const path = String(request.url ?? '').split('?')[0]
        if (!path.startsWith('/api/voice/')) { next(); return }
        const method = String(request.method ?? 'GET').toUpperCase()
        const origin = request.headers.origin
        if (request.headers.host !== '127.0.0.1:5173' ||
          (origin !== undefined && origin !== 'http://127.0.0.1:5173') ||
          request.headers['sec-fetch-site'] === 'cross-site' ||
          (method === 'POST' && origin !== 'http://127.0.0.1:5173')) {
          send(response, 403, { detail: 'La voix est réservée à l’interface locale de Léa.' }); return
        }
        const action = ({ '/api/voice/status': 'status', '/api/voice/transcribe': 'transcribe', '/api/voice/speak': 'speak' } as Record<string, string>)[path]
        if (!action) { send(response, 404, { detail: 'Opération vocale inconnue.' }); return }
        if (method !== (action === 'status' ? 'GET' : 'POST')) { send(response, 405, { detail: 'Méthode refusée.' }); return }
        if (method === 'POST' && request.headers['content-type']?.split(';')[0] !== 'application/json') {
          send(response, 415, { detail: 'Une requête JSON est requise.' }); return
        }
        if (active) { send(response, 409, { detail: 'Un traitement vocal est déjà en cours.' }); return }
        void invoke(action, request, response)
      })
    },
  }
}

import type { Plugin } from 'vite'

type SpawnProcess = (command: string, args: string[], options: unknown) => any
type PreferenceReply = { status: number; body: unknown }

// Le projet n'installe pas de types Node globaux ; seule cette API serveur est utilisée.
const timers = globalThis as unknown as {
  setTimeout(callback: () => void, milliseconds: number): unknown
  clearTimeout(handle: unknown): void
}

// Le contrôleur existant de Vite reste le seul serveur lorsque le cœur est arrêté.
export function preferencesController(spawnProcess: SpawnProcess): Plugin {
  let projectRoot = ''
  let saving = false

  // Ferme le protocole HTTP et interdit la mise en cache de valeurs personnelles.
  function send(response: any, status: number, body: unknown) {
    response.statusCode = status
    response.setHeader('Content-Type', 'application/json; charset=utf-8')
    response.setHeader('Cache-Control', 'no-store')
    response.setHeader('X-Content-Type-Options', 'nosniff')
    response.end(JSON.stringify(body))
  }

  // Transmet uniquement le JSON sur stdin, jamais dans une commande ou un chemin.
  function invoke(action: 'read' | 'save', body: string): Promise<PreferenceReply> {
    return new Promise((resolve, reject) => {
      const child = spawnProcess(
        `${projectRoot}/backend/.venv/Scripts/python.exe`,
        ['-B', `${projectRoot}/tools/preferences.py`, action],
        { cwd: projectRoot, shell: false, windowsHide: true },
      )
      let output = ''
      let settled = false
      // Une sortie incorrecte ne devient jamais une confirmation de sauvegarde.
      function fail() {
        if (settled) return
        settled = true
        timers.clearTimeout(timer)
        child.kill()
        reject(new Error('Contrôleur de préférences indisponible. Rechargez pour vérifier le dernier choix enregistré.'))
      }
      const timer = timers.setTimeout(fail, 15_000)
      child.once('error', fail)
      child.stdin.on('error', fail)
      // Le diagnostic privé n'est jamais recopié dans la réponse HTTP.
      child.stderr.on('data', () => {})
      child.stdout.on('data', (chunk: unknown) => {
        if (settled) return
        output += String(chunk)
        if (output.length > 16_384) fail()
      })
      // Attend la fermeture des flux pour analyser le JSON complet.
      child.once('close', (exitCode: number | null) => {
        if (settled) return
        try {
          const reply = JSON.parse(output) as PreferenceReply
          if (exitCode !== 0 || ![200, 409, 422, 503].includes(reply.status) || !reply.body) {
            fail()
            return
          }
          settled = true
          timers.clearTimeout(timer)
          resolve(reply)
        } catch {
          fail()
        }
      })
      child.stdin.end(body)
    })
  }

  // Borne la requête avant de créer un enfant ; aucun payload arbitrairement gros.
  function readBody(request: any): Promise<string> {
    return new Promise((resolve, reject) => {
      let body = ''
      let bytes = 0
      const timer = timers.setTimeout(() => reject(new Error('Délai de requête dépassé.')), 10_000)
      request.on('data', (chunk: { length: number; toString(): string }) => {
        bytes += chunk.length
        if (bytes <= 1024) body += chunk.toString()
      })
      request.once('end', () => {
        timers.clearTimeout(timer)
        if (bytes > 1024) reject(new Error('Requête trop grande.'))
        else resolve(body)
      })
      // Termine le délai même si le navigateur ferme sa connexion avant le corps.
      function interrupted() {
        timers.clearTimeout(timer)
        reject(new Error('Requête interrompue.'))
      }
      request.once('aborted', interrupted)
      request.once('error', interrupted)
    })
  }

  return {
    name: 'lea-preferences-controller',
    apply: 'serve',
    // La racine provient de Vite, jamais d'un champ envoyé par le navigateur.
    configResolved(config) {
      projectRoot = config.root
    },
    // Une seule route dédiée, sans démarrage de FastAPI, modèle ou Docker.
    configureServer(server) {
      server.middlewares.use((request: any, response: any, next: any) => {
        if (String(request.url ?? '').split('?')[0] !== '/api/preferences') {
          next()
          return
        }
        const method = String(request.method ?? 'GET').toUpperCase()
        const origin = request.headers.origin
        if (
          request.headers.host !== '127.0.0.1:5173' ||
          (origin !== undefined && origin !== 'http://127.0.0.1:5173') ||
          request.headers['sec-fetch-site'] === 'cross-site' ||
          (method === 'POST' && origin !== 'http://127.0.0.1:5173')
        ) {
          send(response, 403, { detail: 'Cette opération doit venir de l’interface locale de Léa.' })
          return
        }
        if (!['GET', 'POST'].includes(method)) {
          send(response, 405, { detail: 'Seuls GET et POST sont autorisés.' })
          return
        }
        if (method === 'POST' && request.headers['content-type']?.split(';')[0] !== 'application/json') {
          send(response, 415, { detail: 'Une requête JSON est requise.' })
          return
        }
        if (method === 'POST' && saving) {
          send(response, 409, { detail: 'Un enregistrement est déjà en cours. Réessayez ensuite.' })
          return
        }
        if (method === 'POST') saving = true
        // Le verrou couvre lecture, validation et commit, y compris les erreurs.
        void (async () => {
          try {
            let body = ''
            if (method === 'POST') {
              try {
                body = await readBody(request)
              } catch {
                send(response, 422, { detail: 'Requête invalide, interrompue ou trop grande.' })
                return
              }
            }
            const reply = await invoke(method === 'GET' ? 'read' : 'save', body)
            send(response, reply.status, reply.body)
          } catch {
            send(response, 503, { detail: 'Contrôleur de préférences indisponible. Rechargez pour vérifier le dernier choix enregistré.' })
          } finally {
            if (method === 'POST') saving = false
          }
        })()
      })
    },
  }
}

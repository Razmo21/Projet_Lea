import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

type CoreAction = 'start-core' | 'status-core' | 'stop-core'

type CoreStatus = {
  state: 'stopped' | 'starting' | 'ready' | 'error'
  model: string
  backend: string
  message: string
}

type LeaCommandResult = {
  exitCode: number | null
  stdout: string
  stderr: string
}

type SpawnProcess = (command: string, args: string[], options: unknown) => any

const allowedOrigins = new Set(['http://127.0.0.1:5173'])
const nodeEnvironment = (
  globalThis as { process?: { env?: Record<string, string | undefined> } }
).process?.env
const powerShellExecutable = `${nodeEnvironment?.SystemRoot ?? 'C:\\Windows'}\\System32\\WindowsPowerShell\\v1.0\\powershell.exe`
const localSecurityHeaders = {
  'Cache-Control': 'no-store',
  'Content-Security-Policy': "frame-ancestors 'none'",
  'Referrer-Policy': 'no-referrer',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
}

// Expose uniquement trois commandes locales bornées pendant le développement Vite.
function coreController(spawnProcess: SpawnProcess): Plugin {
  let projectRoot = ''
  let operationInProgress = false

  // Envoie un statut non mis en cache avec une forme unique pour toutes les routes.
  function sendJson(response: any, statusCode: number, body: CoreStatus) {
    response.statusCode = statusCode
    response.setHeader('Content-Type', 'application/json; charset=utf-8')
    response.setHeader('Cache-Control', 'no-store')
    response.end(JSON.stringify(body))
  }

  // Lance le script fixe avec des arguments choisis dans une table fermée.
  function runLea(action: CoreAction, json = false): Promise<LeaCommandResult> {
    const argumentsByAction: Record<CoreAction, string[]> = {
      'start-core': ['start-core'],
      'status-core': ['status-core', '-Json'],
      'stop-core': ['stop-core'],
    }
    const actionArguments = argumentsByAction[action]
    const argumentsToRun = [
      '-NoLogo',
      '-NoProfile',
      '-NonInteractive',
      '-ExecutionPolicy',
      'Bypass',
      '-File',
      `${projectRoot}\\lea.ps1`,
      ...actionArguments,
    ]

    if (json && action !== 'status-core') {
      argumentsToRun.push('-Json')
    }

    // Encadre le processus enfant pour ne résoudre la promesse qu'une seule fois.
    return new Promise((resolve, reject) => {
      const child = spawnProcess(powerShellExecutable, argumentsToRun, {
        cwd: projectRoot,
        shell: false,
        windowsHide: true,
      })
      let stdout = ''
      let stderr = ''
      let settled = false

      // Ignore les événements d'erreur tardifs après la résolution du processus.
      function rejectOnce(error: Error) {
        if (!settled) {
          settled = true
          reject(error)
        }
      }

      // Publie ensemble le code de sortie et les deux flux entièrement accumulés.
      function resolveOnce(exitCode: number | null) {
        if (!settled) {
          settled = true
          resolve({ exitCode, stdout, stderr })
        }
      }

      // Accumule stdout sans l'interpréter avant la fin du processus.
      child.stdout.on('data', (chunk: unknown) => {
        stdout += String(chunk)
      })
      // Conserve stderr pour le diagnostic local sans l'exposer au navigateur.
      child.stderr.on('data', (chunk: unknown) => {
        stderr += String(chunk)
      })
      child.once('error', rejectOnce)
      // Le statut ne lance aucun enfant : attendre `close` garantit alors que
      // son unique ligne JSON est entièrement lue. Pour start/stop, `exit`
      // évite d'attendre d'éventuels handles encore détenus par les enfants
      // que PowerShell vient de lancer ou d'arrêter.
      if (action === 'status-core') {
        child.once('close', resolveOnce)
      } else {
        child.once('exit', resolveOnce)
      }
    })
  }

  // Relit le statut JSON produit par le lanceur et vérifie tous ses champs publics.
  async function readCoreStatus(): Promise<CoreStatus> {
    const result = await runLea('status-core', true)
    let status: CoreStatus

    try {
      status = JSON.parse(result.stdout.trim()) as CoreStatus
    } catch {
      throw new Error('Le contrôleur local n’a pas reçu un état valide de Léa.')
    }

    if (
      typeof status.state !== 'string' ||
      typeof status.model !== 'string' ||
      typeof status.backend !== 'string' ||
      typeof status.message !== 'string'
    ) {
      throw new Error('Le contrôleur local a reçu un état incomplet de Léa.')
    }

    return status
  }

  // Produit un message public stable sans recopier la sortie PowerShell sensible.
  function failureStatus(action: CoreAction): CoreStatus {
    const actionLabel = action === 'start-core' ? 'Le démarrage' : 'L’arrêt'
    return {
      state: 'error',
      model: 'error',
      backend: 'error',
      message: `${actionLabel} du cœur de Léa a échoué. Consultez les journaux locaux.`,
    }
  }

  return {
    name: 'lea-core-controller',
    apply: 'serve',
    // Fige la racine réellement résolue par Vite avant toute commande locale.
    configResolved(config) {
      projectRoot = config.root
    },
    // Installe le middleware de contrôle seulement sur le serveur de développement.
    configureServer(server) {
      // Laisse passer toutes les routes qui n'appartiennent pas au contrôleur local.
      server.middlewares.use((request: any, response: any, next: any) => {
        const path = String(request.url ?? '').split('?')[0]
        const method = String(request.method ?? 'GET').toUpperCase()
        const actionByPath: Record<string, CoreAction> = {
          '/api/core/start': 'start-core',
          '/api/core/stop': 'stop-core',
        }

        if (path === '/api/core/status') {
          if (method !== 'GET') {
            sendJson(response, 405, {
              state: 'error',
              model: 'error',
              backend: 'error',
              message: 'Cette route accepte uniquement GET.',
            })
            return
          }

          // Répond seulement après validation de la sortie JSON complète.
          void readCoreStatus()
            .then((status) => sendJson(response, 200, status))
            .catch(() =>
              sendJson(response, 500, {
                state: 'error',
                model: 'error',
                backend: 'error',
                message: 'Le contrôleur local ne peut pas lire l’état de Léa.',
              }),
            )
          return
        }

        const action = actionByPath[path]
        if (action === undefined) {
          next()
          return
        }

        if (method !== 'POST') {
          sendJson(response, 405, {
            state: 'error',
            model: 'error',
            backend: 'error',
            message: 'Cette route accepte uniquement POST.',
          })
          return
        }

        const origin = request.headers.origin
        if (typeof origin !== 'string' || !allowedOrigins.has(origin)) {
          sendJson(response, 403, {
            state: 'error',
            model: 'error',
            backend: 'error',
            message: 'Cette opération doit venir de l’interface locale de Léa.',
          })
          return
        }

        if (operationInProgress) {
          sendJson(response, 409, {
            state: 'starting',
            model: 'starting',
            backend: 'starting',
            message: 'Une opération sur le cœur de Léa est déjà en cours.',
          })
          return
        }

        operationInProgress = true
        // Maintient le verrou jusqu'à la fin, y compris lorsque la commande échoue.
        void runLea(action)
          .then(async (result) => {
            if (result.exitCode !== 0) {
              sendJson(response, 500, failureStatus(action))
              return
            }

            sendJson(response, 200, await readCoreStatus())
          })
          .catch(() => sendJson(response, 500, failureStatus(action)))
          .finally(() => {
            operationInProgress = false
          })
      })
    },
  }
}

const childProcessModule: string = 'node:child_process'

// Charge `child_process` uniquement dans Node et injecte sa fonction testable au plugin.
export default defineConfig(async () => {
  const childProcess: { spawn: SpawnProcess } = await import(childProcessModule)

  return {
    plugins: [react(), coreController(childProcess.spawn)],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      // Empêche une page distante d'encadrer l'interface locale ou de réutiliser son contenu en cache.
      headers: localSecurityHeaders,
      watch: {
        ignored: ['**/.lea/**', '**/.test-runtime/**', '**/data/**'],
      },
    },
  }
})

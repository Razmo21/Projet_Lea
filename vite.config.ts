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

function coreController(spawnProcess: SpawnProcess): Plugin {
  let projectRoot = ''
  let operationInProgress = false

  function sendJson(response: any, statusCode: number, body: CoreStatus) {
    response.statusCode = statusCode
    response.setHeader('Content-Type', 'application/json; charset=utf-8')
    response.setHeader('Cache-Control', 'no-store')
    response.end(JSON.stringify(body))
  }

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

    return new Promise((resolve, reject) => {
      const child = spawnProcess('powershell.exe', argumentsToRun, {
        cwd: projectRoot,
        shell: false,
        windowsHide: true,
      })
      let stdout = ''
      let stderr = ''
      let settled = false

      function rejectOnce(error: Error) {
        if (!settled) {
          settled = true
          reject(error)
        }
      }

      function resolveOnce(exitCode: number | null) {
        if (!settled) {
          settled = true
          resolve({ exitCode, stdout, stderr })
        }
      }

      child.stdout.on('data', (chunk: unknown) => {
        stdout += String(chunk)
      })
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
    configResolved(config) {
      projectRoot = config.root
    },
    configureServer(server) {
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

export default defineConfig(async () => {
  const childProcess: { spawn: SpawnProcess } = await import(childProcessModule)

  return {
    plugins: [react(), coreController(childProcess.spawn)],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      watch: {
        ignored: ['**/.lea/**', '**/.test-runtime/**', '**/data/**'],
      },
    },
  }
})

import { spawn, ChildProcess } from 'child_process'
import { join } from 'path'
import net from 'net'
import { app } from 'electron'

let pythonProcess: ChildProcess | null = null

function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as net.AddressInfo).port
      server.close(() => resolve(port))
    })
    server.on('error', reject)
  })
}

function findPython(): string {
  // In packaged app, use bundled backend binary
  if (app.isPackaged) {
    const ext = process.platform === 'win32' ? '.exe' : ''
    return join(process.resourcesPath, 'backend', `backend${ext}`)
  }
  // In dev, prefer the venv if it exists, fall back to system python.
  // Try .venv.nosync first (iCloud-safe), then .venv as fallback.
  const fs = require('fs')
  const candidates = process.platform === 'win32'
    ? [
        join(__dirname, '../../backend/.venv.nosync/Scripts/python.exe'),
        join(__dirname, '../../backend/.venv/Scripts/python.exe'),
      ]
    : [
        join(__dirname, '../../backend/.venv.nosync/bin/python3'),
        join(__dirname, '../../backend/.venv/bin/python3'),
      ]
  for (const candidate of candidates) {
    try {
      fs.accessSync(candidate)
      return candidate
    } catch {}
  }
  return process.platform === 'win32' ? 'python' : 'python3'
}

export async function startPythonBackend(geminiApiKey = ''): Promise<string> {
  const port = await getFreePort()
  const pythonExe = findPython()

  const args = app.isPackaged ? [] : [join(__dirname, '../../backend/main.py')]

  // Playwright browsers path: bundled inside app resources (no system Chrome needed)
  // In dev mode, use the system playwright cache so headless_shell issues don't block testing
  const playwrightBrowsersPath = app.isPackaged
    ? join(process.resourcesPath, 'pw-browsers')
    : join(require('os').homedir(), '.cache', 'ms-playwright')

  console.log(`[Bridge] Starting Python: ${pythonExe} ${args.join(' ')} PORT=${port}`)
  console.log(`[Bridge] Playwright browsers: ${playwrightBrowsersPath}`)

  pythonProcess = spawn(pythonExe, args, {
    env: {
      ...process.env,
      PORT: String(port),
      // Tell Playwright where to find the bundled Chromium (no system Chrome needed)
      PLAYWRIGHT_BROWSERS_PATH: playwrightBrowsersPath,
      // Forward stored API key so backend can use it without needing .env
      ...(geminiApiKey ? { GEMINI_API_KEY: geminiApiKey } : {}),
      // Isolate from conda: prevent conda's native .so files from polluting the venv
      CONDA_PREFIX: '',
      CONDA_DEFAULT_ENV: '',
      PYTHONNOUSERSITE: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    // uvicorn logs go to stderr — useful for debugging
    try { process.stderr.write(`[Python] ${data}`) } catch {}
  })

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Python backend did not start within 15 seconds'))
    }, 15_000)

    pythonProcess!.stdout?.on('data', (data: Buffer) => {
      const text = data.toString()
      try { process.stdout.write(`[Python] ${text}`) } catch {}
      if (text.includes(`PORT=${port}`)) {
        clearTimeout(timeout)
        resolve(`http://127.0.0.1:${port}`)
      }
    })

    pythonProcess!.on('exit', (code) => {
      clearTimeout(timeout)
      if (code !== 0 && code !== null) {
        reject(new Error(`Python exited with code ${code}`))
      }
    })

    pythonProcess!.on('error', (err) => {
      clearTimeout(timeout)
      reject(new Error(`Failed to spawn Python: ${err.message}`))
    })
  })
}

export function stopPythonBackend(): void {
  if (pythonProcess) {
    pythonProcess.kill()
    pythonProcess = null
    console.log('[Bridge] Python backend stopped')
  }
}

import { app, BrowserWindow, ipcMain, shell } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { startPythonBackend, stopPythonBackend } from './pythonBridge'
// @ts-ignore — electron-store is CJS
import Store from 'electron-store'

const store = new Store()
let backendUrl: string | null = null

async function createWindow(): Promise<void> {
  const mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
    },
  })

  mainWindow.on('ready-to-show', () => mainWindow.show())

  // Open external links in default browser, not in Electron
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

// Backend URL (for renderer → fetch calls)
ipcMain.handle('get-backend-url', () => backendUrl)

// Persistent settings store (survives app updates, stored in user data dir)
ipcMain.handle('store-get', (_event, key: string) => store.get(key))
ipcMain.handle('store-set', (_event, key: string, value: unknown) => {
  store.set(key, value)
  // If the user just saved a new API key, forward it to the running Python process
  // so it takes effect without requiring a restart.
  if (key === 'gemini_api_key' && backendUrl) {
    fetch(`${backendUrl}/api/settings/api-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: value }),
    }).catch(() => {/* backend may not be ready yet */})
  }
})

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  // Pass the stored Gemini API key to the Python backend as an env var
  const storedApiKey = (store.get('gemini_api_key') as string | undefined) ?? ''

  try {
    backendUrl = await startPythonBackend(storedApiKey)
    console.log(`[Main] Backend ready at ${backendUrl}`)
  } catch (err) {
    console.error('[Main] Failed to start Python backend:', err)
    // Still open the window — it will show an error / settings prompt
  }

  await createWindow()

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  stopPythonBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  stopPythonBackend()
})

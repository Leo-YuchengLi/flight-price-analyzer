import { contextBridge, ipcRenderer } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

const api = {
  getBackendUrl: (): Promise<string | null> => ipcRenderer.invoke('get-backend-url'),
  // Persistent settings (electron-store — survives app updates)
  storeGet: (key: string): Promise<unknown> => ipcRenderer.invoke('store-get', key),
  storeSet: (key: string, value: unknown): Promise<void> => ipcRenderer.invoke('store-set', key, value),
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (non-context-isolated fallback, dev only)
  window.electron = electronAPI
  // @ts-ignore
  window.api = api
}

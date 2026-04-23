/// <reference types="vite/client" />
import { ElectronAPI } from '@electron-toolkit/preload'

declare global {
  interface Window {
    electron: ElectronAPI
    api?: {
      getBackendUrl: () => Promise<string | null>
      storeGet: (key: string) => Promise<unknown>
      storeSet: (key: string, value: unknown) => Promise<void>
    }
  }
}

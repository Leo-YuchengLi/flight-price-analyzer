import { useState, useEffect } from 'react'

export type BackendStatus = 'connecting' | 'connected' | 'error'

export interface BackendState {
  url: string | null
  status: BackendStatus
  error: string | null
}

export function useBackend(): BackendState {
  const [state, setState] = useState<BackendState>({
    url: null,
    status: 'connecting',
    error: null,
  })

  useEffect(() => {
    let cancelled = false

    async function connect() {
      try {
        // In Electron, use the preload bridge; in browser dev mode fall back to fixed port
        const url = (typeof window.api !== 'undefined')
          ? await window.api.getBackendUrl()
          : 'http://127.0.0.1:8765'
        if (cancelled) return

        if (!url) {
          setState({ url: null, status: 'error', error: 'Python backend failed to start' })
          return
        }

        const res = await fetch(`${url}/ping`)
        if (cancelled) return

        const data = await res.json()
        if (data.ok) {
          setState({ url, status: 'connected', error: null })
        } else {
          setState({ url, status: 'error', error: 'Backend returned unexpected response' })
        }
      } catch (err) {
        if (!cancelled) {
          setState({ url: null, status: 'error', error: String(err) })
        }
      }
    }

    connect()
    return () => { cancelled = true }
  }, [])

  return state
}

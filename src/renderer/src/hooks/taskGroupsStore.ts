/**
 * Module-level singleton for TaskGroupsSearch state.
 * Lives outside React so it survives page navigation (component unmount/remount).
 * The worker Promise loop writes directly to this store; the React component
 * subscribes and mirrors state locally for rendering.
 */

export type TGTaskStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped'

export interface TGTask {
  id: string
  groupLabel: string
  origin: string
  destination: string
  trip_type: string
  dates: string[]
  return_dates: string[]
  dateRanges: { start: string; end: string }[]
  cabin: string
  status: TGTaskStatus
  flightCount: number
  error?: string
}

export interface TGState {
  title: string
  checkpointId: string
  tasks: TGTask[]
  running: boolean
  done: boolean
  allFlightsCount: number
  reportId: string | null
}

// ── Store internals ───────────────────────────────────────────────────────────

// Persists the full init object so ClassicSearchPage can restore TaskGroupsSearch
// after the user navigates away and comes back (component remounts, state is lost)
let _savedInit: unknown | null = null

let _state: TGState | null = null
let _abort: AbortController | null = null
const _allFlights: object[] = []
const _checkpointedFlights = { current: 0 }
const _subs = new Set<() => void>()
const _notify = () => _subs.forEach(f => f())

// ── Public API ────────────────────────────────────────────────────────────────

export const taskGroupsStore = {

  get(): TGState | null { return _state },

  getFlights(): object[] { return [..._allFlights] },

  isRunning(): boolean { return _state?.running ?? false },

  setInit(init: unknown): void { _savedInit = init },
  getInit(): unknown | null { return _savedInit },

  /** Call before startAll(). Sets up fresh state. */
  init(title: string, checkpointId: string, tasks: TGTask[]): void {
    _allFlights.length = 0
    _checkpointedFlights.current = 0
    _abort = null
    _state = {
      title, checkpointId,
      tasks: tasks.map(t => ({ ...t, status: 'pending', flightCount: 0, error: undefined })),
      running: false, done: false, allFlightsCount: 0, reportId: null,
    }
    _notify()
  },

  /** Returns the AbortController for the new run. */
  startRun(): AbortController {
    if (!_state) throw new Error('taskGroupsStore: not initialized')
    _abort = new AbortController()
    _state = { ..._state, running: true, done: false }
    _notify()
    return _abort
  },

  getSignal(): AbortSignal | null { return _abort?.signal ?? null },

  updateTask(id: string, patch: Partial<TGTask>): void {
    if (!_state) return
    _state = { ..._state, tasks: _state.tasks.map(t => t.id === id ? { ...t, ...patch } : t) }
    _notify()
  },

  addFlights(flights: object[]): void {
    _allFlights.push(...flights)
    if (_state) _state = { ..._state, allFlightsCount: _allFlights.length }
    _notify()
  },

  getNewFlights(): object[] {
    const newOnes = _allFlights.slice(_checkpointedFlights.current)
    _checkpointedFlights.current = _allFlights.length
    return newOnes
  },

  setReportId(id: string): void {
    if (!_state) return
    _state = { ..._state, reportId: id }
    _notify()
  },

  finish(): void {
    if (!_state) return
    _abort = null
    _state = { ..._state, running: false, done: true }
    _notify()
  },

  abort(): void {
    _abort?.abort()
    if (_state) _state = { ..._state, running: false }
    _notify()
  },

  subscribe(fn: () => void): () => void {
    _subs.add(fn)
    return () => _subs.delete(fn)
  },

  clear(): void {
    _abort?.abort()
    _abort = null
    _allFlights.length = 0
    _checkpointedFlights.current = 0
    _state = null
    _notify()
  },
}

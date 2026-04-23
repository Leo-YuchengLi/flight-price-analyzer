/**
 * Module-level singleton: holds the currently running search task state.
 * Lives outside React so it survives page navigation (component unmount/remount).
 */

export interface TaskProgress {
  msg: string
  cur: number
  total: number
}

export interface TaskInfo {
  label: string
  running: boolean
  done: boolean
  progress: TaskProgress
  log: string[]
  flightCount: number
  reportId: string | null
}

// ── Store ─────────────────────────────────────────────────────────────────────

let _task: (TaskInfo & { _abortFn: () => void }) | null = null
const _subs = new Set<() => void>()
const _notify = () => _subs.forEach(f => f())

// Shared flights array — persists across navigation so BatchSearch can auto-save
export let sharedFlights: object[] = []

export const searchTaskStore = {
  get(): TaskInfo | null {
    if (!_task) return null
    const { _abortFn: _, ...rest } = _task
    return rest
  },

  isRunning(): boolean { return _task?.running ?? false },

  start(label: string, abortFn: () => void): void {
    sharedFlights = []
    _task = {
      label, running: true, done: false,
      progress: { msg: '', cur: 0, total: 0 },
      log: [], flightCount: 0, reportId: null,
      _abortFn: abortFn,
    }
    _notify()
  },

  updateProgress(progress: TaskProgress): void {
    if (!_task) return
    _task.progress = progress
    _notify()
  },

  addLog(msg: string): void {
    if (!_task) return
    _task.log = [..._task.log.slice(-100), msg]
    _notify()
  },

  updateFlightCount(n: number): void {
    if (!_task) return
    _task.flightCount = n
    _notify()
  },

  setReportId(id: string): void {
    if (!_task) return
    _task.reportId = id
    _notify()
  },

  finish(): void {
    if (!_task) return
    _task.running = false
    _task.done = true
    _notify()
  },

  abort(): void {
    if (!_task) return
    _task._abortFn()
    _task.running = false
    _notify()
  },

  clear(): void { _task = null; sharedFlights = []; _notify() },

  subscribe(fn: () => void): () => void {
    _subs.add(fn)
    return () => _subs.delete(fn)
  },
}

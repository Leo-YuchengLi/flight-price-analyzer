import { useEffect, useReducer } from 'react'
import { searchTaskStore, TaskInfo } from './searchTaskStore'

/** Subscribes a component to the global search task store. */
export function useSearchTask(): TaskInfo | null {
  const [, forceUpdate] = useReducer(x => x + 1, 0)
  useEffect(() => searchTaskStore.subscribe(forceUpdate), [])
  return searchTaskStore.get()
}

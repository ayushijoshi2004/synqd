import { useEffect, useState } from "react"

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

// Pass a stable service function, or useCallback when a request needs an ID.
// Ignore stale responses after navigation or a changed request.
export function useAsyncData<T>(load: () => Promise<T>): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    error: null,
  })

  useEffect(() => {
    let active = true
    setState({ data: null, loading: true, error: null })

    async function run() {
      try {
        const data = await load()
        if (active) setState({ data, loading: false, error: null })
      } catch (error) {
        if (active) {
          setState({
            data: null,
            loading: false,
            error:
              error instanceof Error ? error.message : "Unable to load data.",
          })
        }
      }
    }

    void run()
    return () => {
      active = false
    }
  }, [load])

  return state
}

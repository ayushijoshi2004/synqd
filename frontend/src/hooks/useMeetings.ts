import { useEffect, useSyncExternalStore } from "react"
import {
  getMeetings,
  getMeetingsSnapshot,
  subscribeMeetings,
} from "../services/meetings"

export function useMeetings() {
  useEffect(() => {
    getMeetings().catch((error) => {
      console.error("Failed to load meetings:", error)
    })
  }, [])

  return useSyncExternalStore(subscribeMeetings, getMeetingsSnapshot)
}
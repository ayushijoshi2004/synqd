import { config } from "../config/env"
import { applyMeetingResponse, normalizeMeetingResponse } from "./meetings"
import type { Meeting } from "../types/meeting"

const pending = new Map<string, Promise<Meeting>>()
async function mutate(meetingId: string, operation: "join" | "end"): Promise<Meeting> {
  const key = `${meetingId}:${operation}`
  const existing = pending.get(key)
  if (existing) return existing
  const task = (async () => {
    const path = operation === "join" ? "/meetings/join" : `/meetings/${encodeURIComponent(meetingId)}/transcription/end`
    const response = await fetch(`${config.apiBaseUrl}${path}`, {
      method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" },
      ...(operation === "join" ? { body: JSON.stringify({ synqMeetingId: meetingId }) } : {}),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data?.error?.message || "Unable to update transcription. Refresh and retry.")
    const meeting = data as Meeting
    applyMeetingResponse(normalizeMeetingResponse(meeting))
    return meeting
  })()
  pending.set(key, task)
  try { return await task } finally { pending.delete(key) }
}
export const joinMeeting = (meetingId: string) => mutate(meetingId, "join")
export const endTranscription = (meetingId: string) => mutate(meetingId, "end")

export function safeMeetUrl(value?: string): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    if (url.protocol === "https:" && url.host === "meet.google.com" && !url.username && !url.password && /^\/[a-z]{3}-[a-z]{4}-[a-z]{3}\/?$/.test(url.pathname)) return url.href
  } catch { /* Invalid stored links must never be opened. */ }
}

export async function saveMeetUrl(meetingId: string, googleMeetUrl: string): Promise<void> {
  const value = googleMeetUrl.trim()
  if (value && !safeMeetUrl(value)) throw new Error("Enter a valid HTTPS Google Meet link.")
  const response = await fetch(`${config.apiBaseUrl}/meetings/${encodeURIComponent(meetingId)}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ googleMeetUrl: value }),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data?.error?.message || "Unable to save the Meet link.")
  applyMeetingResponse(normalizeMeetingResponse(data as Meeting))
}

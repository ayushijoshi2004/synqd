import { config } from "../config/env"
import { applyMeetingResponse, getMeetingsSnapshot } from "./meetings"
import type { Meeting } from "../types/meeting"

export interface CalendarConnection {
  configured: boolean
  connected: boolean
  timeZone?: string
  error?: string
}
export const googleAuthorizationUrl = `${config.apiBaseUrl}/google-calendar/authorize`

export async function getGoogleCalendarStatus(): Promise<CalendarConnection> {
  const response = await fetch(`${config.apiBaseUrl}/google-calendar/status`, { cache: "no-store" })
  if (!response.ok) throw new Error("Unable to check Google Calendar connection.")
  return response.json() as Promise<CalendarConnection>
}

const pending = new Set<string>()
export async function retryGoogleCalendar(sourceId: string, followUpId: string): Promise<void> {
  const key = `${sourceId}/${followUpId}`
  if (pending.has(key)) return
  pending.add(key)
  try {
    const response = await fetch(`${config.apiBaseUrl}/meetings/${encodeURIComponent(sourceId)}/follow-ups/${encodeURIComponent(followUpId)}/google-calendar`, { method: "POST" })
    if (!response.ok) throw new Error(`Unable to create Google Calendar event: ${response.status}`)
    const meeting: Meeting = await response.json()
    const current = getMeetingsSnapshot().meetings.find((item) => item.id === meeting.id)
    if (current) applyMeetingResponse({ ...current, ...meeting })
    if (meeting.googleCalendar?.status !== "created")
      throw new Error(meeting.googleCalendar?.error || "Google Calendar creation is incomplete. Your Synq meeting is saved.")
  } finally {
    pending.delete(key)
  }
}

export function googleEventUrl(meeting: Meeting): string | undefined {
  if (meeting.googleCalendar?.status !== "created" || !meeting.googleCalendar.eventId) return undefined
  try {
    const url = new URL(meeting.googleCalendar.eventUrl || "")
    if (url.protocol === "https:" && ["calendar.google.com", "www.google.com"].includes(url.hostname) && !url.username) return url.href
  } catch { /* No guessed URLs. */ }
  return undefined
}

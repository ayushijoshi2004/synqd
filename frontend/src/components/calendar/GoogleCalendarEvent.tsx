import { useState } from "react"
import type { Meeting } from "../../types/meeting"
import { googleEventUrl, retryGoogleCalendar } from "../../services/googleCalendar"
import { btnGhost } from "../ui"

export default function GoogleCalendarEvent({ meeting, sourceId, followUpId }: {
  meeting: Meeting; sourceId?: string; followUpId?: string
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const url = googleEventUrl(meeting)
  if (url) return <a className={btnGhost} href={url} target="_blank" rel="noopener noreferrer">Open Google Calendar event</a>
  if (!sourceId || !followUpId) return null
  async function retry() {
    if (pending) return
    setPending(true); setError("")
    try { await retryGoogleCalendar(sourceId!, followUpId!) }
    catch (error) { setError(error instanceof Error ? error.message : "Unable to create Calendar event.") }
    finally { setPending(false) }
  }
  return <div className="space-y-2 text-[12px]">
    <p role={error || meeting.googleCalendar?.status === "failed" ? "alert" : undefined} className="text-mute">
      {error || meeting.googleCalendar?.error || "Synq meeting saved. Its Google Calendar event has not been confirmed."}
    </p>
    <button className={btnGhost} disabled={pending} onClick={() => void retry()}>
      {pending ? "Creating Calendar event…" : meeting.googleCalendar?.status === "failed" || meeting.googleCalendar?.status === "pending" ? "Retry Google Calendar" : "Create Google Calendar event"}
    </button>
  </div>
}

import { useEffect, useRef, useState } from "react"
import type { MeetingDetail } from "../../types/meeting"
import { refreshMeeting } from "../../services/meetings"
import { endTranscription, joinMeeting, safeMeetUrl, saveMeetUrl } from "../../services/vexa"
import { btnPrimary } from "../ui"

export default function TranscriptionControls({ meeting }: { meeting: MeetingDetail }) {
  const [busy, setBusy] = useState<"join" | "end" | "save" | "">("")
  const requestInFlight = useRef(false)
  const [error, setError] = useState("")
  const [refreshError, setRefreshError] = useState("")
  const [editing, setEditing] = useState(false)
  const [link, setLink] = useState(meeting.googleMeetUrl ?? "")
  const state = meeting.transcription
  const status = state?.status ?? "not_started"
  const active = ["starting", "transcribing", "stopping"].includes(status)
  const url = safeMeetUrl(meeting.googleMeetUrl)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>
    async function refresh() {
      let retry = false
      try {
        await refreshMeeting(meeting.id)
        if (!cancelled) setRefreshError("")
      } catch {
        retry = true
        if (!cancelled) setRefreshError("Unable to refresh transcription. Reconnecting automatically; saved content is retained.")
      }
      if (!cancelled && (active || state?.polling || retry)) timer = setTimeout(() => void refresh(), 4000)
    }
    void refresh()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [meeting.id, active, state?.polling])

  async function act(operation: "join" | "end" | "save") {
    if (requestInFlight.current) return
    requestInFlight.current = true
    setBusy(operation); setError("")
    // Reserve a blank tab during the gesture so async API work is not blocked
    // by popup protection. Never navigate it until the backend confirms a bot.
    const tab = operation === "join" ? window.open("about:blank", "_blank") : null
    if (tab) tab.opener = null
    try {
      if (operation === "save") {
        await saveMeetUrl(meeting.id, link)
        setEditing(false)
      } else if (operation === "end") {
        await endTranscription(meeting.id)
      } else {
        const saved = await joinMeeting(meeting.id)
        const target = safeMeetUrl(saved.googleMeetUrl)
        if (!target || !saved.transcription?.botId || saved.transcription.status === "error") {
          tab?.close()
          if (saved.transcription?.status === "starting") setError("Synq AI is already starting. The saved status will refresh automatically.")
          else throw new Error(saved.transcription?.error || "The transcription session could not be confirmed.")
        } else if (tab) tab.location.replace(target)
        else setError("Your browser blocked the meeting tab. Use Open Google Meet below.")
      }
    } catch (err) {
      tab?.close()
      setError(err instanceof Error ? err.message : "Unable to update transcription.")
      await refreshMeeting(meeting.id).catch(() => {})
    } finally {
      requestInFlight.current = false; setBusy("")
    }
  }
  return (
    <div className="mb-3 text-[13px]">
      <div className="flex flex-wrap items-center gap-3">
        {(status === "not_started" || (status === "error" && !state?.attempted)) && (
          <button className={btnPrimary} disabled={!!busy} onClick={() => void act("join")}>
            {busy === "join" ? "Starting transcription..." : "Join Meeting"}
          </button>
        )}
        {status === "starting" && <button className={btnPrimary} disabled>Starting transcription...</button>}
        {(status === "transcribing" || status === "stopping" || (status === "starting" && !!state?.botId) || (status === "error" && !!state?.botId && !state?.terminal)) && (
          <button className={btnPrimary} disabled={!!busy || (status === "stopping" && !state?.error)} onClick={() => void act("end")}>
            {busy === "end" || (status === "stopping" && !state?.error) ? "Ending transcription..." : "End transcription"}
          </button>
        )}
        <span role="status" className="text-mute">
          {status === "starting" ? "Admit Synq AI if Google Meet asks." :
           status === "transcribing" ? "Synq AI is transcribing. Admit Synq AI if Google Meet asks." :
           status === "completed" ? "Transcription completed" :
           status === "stopping" ? "Saving the final transcript..." :
           status === "error" ? "Transcription needs attention" : ""}
        </span>
        {url && <a href={url} target="_blank" rel="noopener noreferrer" className="text-accent">Open Google Meet</a>}
        {!active && !state?.attempted && <button className="text-mute hover:text-ink" onClick={() => { setLink(meeting.googleMeetUrl ?? ""); setEditing(!editing) }}>{url ? "Edit Meet link" : "Add Meet link"}</button>}
      </div>
      {!url && <p className="mt-2 text-mute">This meeting has no valid Google Meet link. Add and save its link before joining.</p>}
      {editing && <form className="mt-2 flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); void act("save") }}>
        <input aria-label="Google Meet link" type="url" value={link} onChange={(event) => setLink(event.target.value)} placeholder="https://meet.google.com/..." className="rounded-lg border border-line bg-bg px-3 py-2 min-w-64" disabled={!!busy} />
        <button className={btnPrimary} disabled={!!busy}>{busy === "save" ? "Saving..." : "Save Meet link"}</button>
        <button type="button" disabled={!!busy} onClick={() => setEditing(false)}>Cancel</button>
      </form>}
      {(error || state?.error) && <p role="alert" className="mt-2 text-red-700">{error || state?.error}</p>}
      {refreshError && <p role="alert" className="mt-2 text-red-700">{refreshError}</p>}
    </div>
  )
}

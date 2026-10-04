import { useEffect, useState } from "react"
import { getGoogleCalendarStatus, googleAuthorizationUrl, type CalendarConnection } from "../../services/googleCalendar"
import { btnGhost } from "../ui"

export default function GoogleCalendarConnection({ onChange }: { onChange?: (status: CalendarConnection) => void }) {
  const [status, setStatus] = useState<CalendarConnection | null>(null)
  const [error, setError] = useState("")
  useEffect(() => {
    let active = true
    const refresh = () => { void getGoogleCalendarStatus().then((value) => {
      if (active) { setStatus(value); setError(""); onChange?.(value) }
    }).catch(() => { if (active) setError("Unable to check Google Calendar connection.") }) }
    refresh()
    window.addEventListener("focus", refresh)
    return () => { active = false; window.removeEventListener("focus", refresh) }
  }, [onChange])
  return <div className="flex flex-wrap items-center gap-2 text-[12px] text-mute mb-3 shrink-0">
    <span>{error || (status?.connected ? "Google Calendar connected" : status ? "Google Calendar not connected" : "Checking Google Calendar…")}</span>
    {status?.timeZone && <span>· {status.timeZone}</span>}
    {status?.configured && <a className={`${btnGhost} h-7 text-[12px]`} href={googleAuthorizationUrl} target="_blank" rel="noopener noreferrer">
      {status.connected ? "Reconnect Google Calendar" : "Connect Google Calendar"}
    </a>}
    {status?.error && <span>{status.error}</span>}
  </div>
}

import { useState, useSyncExternalStore } from "react"
import { ChevronLeft, ChevronRight, Sparkles, Send, Check } from "lucide-react"
import {
  getCalendarView,
  getFollowUpsSnapshot,
  subscribeFollowUps,
  proposeFollowUp,
  approveFollowUp,
  editFollowUp,
  dismissFollowUp,
} from "../services/calendar"
import { useMeetings } from "../hooks/useMeetings"
import { updateMeeting } from "../services/meetings"
import MeetingFormModal from "../components/meetings/MeetingFormModal"
import CalendarMeetingModal from "../components/calendar/CalendarMeetingModal"
import type { CalendarEventKind } from "../types/calendar"
import { addDays, toggleValue, weekOf } from "../utils/calendar"
import { Card, btnGhost, btnPrimary } from "../components/ui"
import CalendarSidebar from "../components/calendar/CalendarSidebar"
import CalendarWeekGrid from "../components/calendar/CalendarWeekGrid"
import GoogleCalendarConnection from "../components/calendar/GoogleCalendarConnection"
import type { CalendarConnection } from "../services/googleCalendar"
import CalendarApprovals from "../components/calendar/CalendarApprovals"

export default function CalendarPage({
  onOpenMeeting,
}: {
  onOpenMeeting: (id: string) => void
}) {
  const { meetings, focusDate } = useMeetings()
  const [googleConnection, setGoogleConnection] = useState<CalendarConnection | null>(null)
  const followUps = useSyncExternalStore(
    subscribeFollowUps,
    getFollowUpsSnapshot,
  )
  const [week, setWeek] = useState(() => weekOf(focusDate))
  const data = getCalendarView(week)
  const events = data.events
  const [hiddenProjects, setHiddenProjects] = useState<string[]>([])
  const selectedProjects = data.projects
    .map((project) => project.name)
    .filter((name) => !hiddenProjects.includes(name))
  const [selectedTypes, setSelectedTypes] = useState<CalendarEventKind[]>([
    "event",
    "proposed",
  ])
  const [selectedId, setSelectedId] = useState("")
  const [dialog, setDialog] =
    useState<"view" | "edit" | "review" | "edit-suggestion" | null>(null)
  const selectedMeeting = meetings.find((meeting) => meeting.id === selectedId)
  const selectedProposal = followUps.find(
    (proposal) => proposal.id === selectedId && proposal.status === "suggested",
  )
  const [input, setInput] = useState("")
  const [note, setNote] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const projectColors = Object.fromEntries(
    data.projects.map((project) => [project.name, project.color]),
  )
  const visible = events.filter(
    (event) =>
      selectedProjects.includes(event.project) &&
      selectedTypes.includes(event.kind),
  )
  const proposals = followUps.filter(
    (proposal) => proposal.status === "suggested",
  )
  const upcoming = events
    .filter(
      (event) =>
        event.kind === "event" &&
        meetings.find((meeting) => meeting.id === event.id)?.status ===
          "scheduled",
    )
    .sort((a, b) => a.day - b.day || a.startHour - b.startHour)
    .slice(0, 3)

  function select(id: string) {
    setSelectedId(id)
    setDialog(
      followUps.some(
        (proposal) => proposal.id === id && proposal.status === "suggested",
      )
        ? "review"
        : "view",
    )
  }

  async function runUpdate(update: () => Promise<void>) {
    if (pending) return
    setPending(true)
    setError(null)
    try {
      await update()
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Unable to update the calendar.",
      )
    } finally {
      setPending(false)
    }
  }

  async function dismiss(id: string) {
    await runUpdate(async () => {
      await dismissFollowUp(id)
      setNote("Suggestion dismissed.")
    })
  }

  async function ask() {
    if (!input.trim()) return
    await runUpdate(async () => {
      const result = await proposeFollowUp(input, week)
      setSelectedId(result.id)
      setNote("Follow-up suggested. Review the details before approving.")
      setInput("")
    })
  }

  return (
    <div className="p-5 lg:px-8  lg:h-[calc(100vh-3.5rem)] lg:flex lg:flex-col lg:overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3 shrink-0">
        <h1 className="text-[24px] font-semibold tracking-tight">
          Team Calendar
        </h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setWeek(addDays(week, -7))}
            className={`${btnGhost} w-8 px-0`}
            aria-label="Previous week"
          >
            <ChevronLeft size={15} />
          </button>
          <span className="text-[13px] font-medium min-w-40 text-center font-mono">
            {data.rangeLabel}
          </span>
          <button
            onClick={() => setWeek(addDays(week, 7))}
            className={`${btnGhost} w-8 px-0`}
            aria-label="Next week"
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>

      <GoogleCalendarConnection onChange={setGoogleConnection} />
      <Card className="mb-3 p-2 shrink-0 flex flex-col sm:flex-row gap-3 sm:items-center border-accent/25">
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-accent pl-2 shrink-0">
          <Sparkles size={14} /> Scheduling assistant
        </span>
        <form
          className="flex flex-1 gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void ask()
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Schedule a follow-up with the design team next week"
            className="flex-1 h-9 rounded-lg border border-line px-3 text-[13px] outline-none focus:border-accent"
          />
          <button
            disabled={pending}
            className={`${btnPrimary} w-9 px-0`}
            aria-label="Send"
          >
            <Send size={14} />
          </button>
        </form>
      </Card>
      {note && (
        <p className="text-[12.5px] text-accent font-medium mb-2 flex items-center gap-1.5 shrink-0">
          <Check size={14} /> {note}
        </p>
      )}

      {error && (
        <p role="alert" className="text-[12.5px] text-mute mb-2">
          {error}
        </p>
      )}
      <div className="grid gap-4 lg:grid-cols-[210px_minmax(0,1fr)_310px] lg:flex-1 lg:min-h-0">
        <CalendarSidebar
          projectOptions={data.projects}
          projectColors={projectColors}
          selectedProjects={selectedProjects}
          selectedTypes={selectedTypes}
          upcoming={upcoming}
          days={data.days}
          onToggleProject={(project) =>
            setHiddenProjects((current) => toggleValue(current, project))
          }
          onToggleType={(type) =>
            setSelectedTypes((current) => toggleValue(current, type))
          }
          onSelect={select}
        />
        <CalendarWeekGrid
          events={visible}
          days={data.days}
          hours={data.hours}
          projectColors={projectColors}
          selectedId={selectedId}
          onSelect={select}
        />
        <CalendarApprovals
          proposals={proposals}
          pending={pending}
          onApprove={(id) => {
            setSelectedId(id)
            setDialog("review")
          }}
          onEdit={(id) => {
            setSelectedId(id)
            setDialog("edit-suggestion")
          }}
          onDismiss={(id) => void dismiss(id)}
        />
      </div>
      {dialog === "view" && selectedMeeting && (
        <CalendarMeetingModal
          meeting={selectedMeeting}
          approvedFollowUp={followUps.find((item) => item.status === "approved" && item.scheduledMeetingId === selectedMeeting.id)}
          onClose={() => setDialog(null)}
          onEdit={() => setDialog("edit")}
          onView={() => onOpenMeeting(selectedMeeting.id)}
        />
      )}
      {dialog === "edit" && selectedMeeting && (
        <MeetingFormModal
          title="Edit Meeting"
          submitLabel="Save Changes"
          initial={selectedMeeting}
          onClose={() => setDialog(null)}
          onSubmit={async (fields) => {
            await updateMeeting(selectedMeeting.id, fields)
            setWeek(weekOf(fields.date))
            setNote("Meeting updated.")
          }}
        />
      )}
      {(dialog === "review" || dialog === "edit-suggestion") &&
        selectedProposal && (
          <MeetingFormModal
            title={dialog === "review" ? "Review follow-up" : "Edit suggestion"}
            submitLabel={
              dialog === "review" ? "Approve & Schedule" : "Save suggestion"
            }
            initial={selectedProposal}
            allowIncomplete={dialog === "edit-suggestion"}
            calendarNotice={googleConnection?.connected
              ? `Approval also creates a Google Calendar event and sends invitations to participant emails. Times use ${googleConnection.timeZone}.`
              : "Approval saves the Synq meeting. Connect Google Calendar to create its event and send invitations."}
            onClose={() => {
              const resolved = getFollowUpsSnapshot().find((item) => item.id === selectedProposal.id)
              if (resolved?.status === "approved" && resolved.scheduledMeetingId) {
                setSelectedId(resolved.scheduledMeetingId)
                setDialog("view")
              } else setDialog(null)
            }}
            onSubmit={async (fields) => {
              if (dialog === "review") {
                const id = await approveFollowUp(selectedProposal.id, fields)
                setSelectedId(id)
                setNote("Follow-up approved and scheduled.")
              } else {
                await editFollowUp(selectedProposal.id, fields)
                setNote("Suggestion updated. Awaiting approval.")
              }
              if (fields.date) setWeek(weekOf(fields.date))
            }}
          />
        )}
    </div>
  )
}

import { useState } from "react"
import GoogleCalendarEvent from "./GoogleCalendarEvent"
import type { FollowUpMeeting, MeetingDetail } from "../../types/meeting"
import { deleteMeeting } from "../../services/meetings"
import {
  aiStatusLabels,
  formatDate,
  formatTimeRange,
  meetingStatusLabels,
} from "../../utils/meetings"
import Modal from "../Modal"
import { Pill, btnGhost, btnPrimary } from "../ui"

export default function CalendarMeetingModal({
  meeting,
  approvedFollowUp,
  onEdit,
  onView,
  onClose,
}: {
  meeting: MeetingDetail
  approvedFollowUp?: FollowUpMeeting
  onEdit: () => void
  onView: () => void
  onClose: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  async function remove() {
    if (pending) return
    setPending(true)
    try {
      await deleteMeeting(meeting.id)
      onClose()
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to delete meeting.",
      )
      setPending(false)
    }
  }
  return (
    <Modal
      title={confirming ? "Delete meeting?" : meeting.title}
      onClose={onClose}
    >
      <div className="p-5 space-y-4 text-[13px]">
        {confirming ? (
          <p>
            Delete “{meeting.title}” from Meetings and Calendar? This cannot be
            undone.
          </p>
        ) : (
          <>
            <div className="flex gap-2">
              <Pill tone={meeting.status}>
                {meetingStatusLabels[meeting.status]}
              </Pill>
              <Pill tone={meeting.aiStatus}>
                {aiStatusLabels[meeting.aiStatus]}
              </Pill>
            </div>
            <p className="font-mono text-mute">
              {formatDate(meeting.date)} · {formatTimeRange(meeting)}
            </p>
            <div>
              <p className="font-medium">Participants</p>
              <p className="text-mute mt-1">
                {meeting.participants.map((person) => person.name).join(", ")}
              </p>
            </div>
            <div>
              <p className="font-medium">Agenda</p>
              <p className="whitespace-pre-wrap text-mute mt-1">
                {meeting.agenda || "No agenda added."}
              </p>
            </div>
            <div className="flex gap-6">
              <p>
                <b>Project:</b> {meeting.project || "None"}
              </p>
              <p>
                <b>Team:</b> {meeting.team || "None"}
              </p>
            </div>
            <GoogleCalendarEvent meeting={meeting} sourceId={approvedFollowUp?.sourceMeetingId} followUpId={approvedFollowUp?.id} />
            {meeting.googleCalendar?.status === "created" && <p className="text-[12px] text-mute">Edits or deletion in Synq do not change the Google event. Manage that event using its link.</p>}
          </>
        )}
        {error && (
          <p role="alert" className="text-red-700">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          {confirming ? (
            <>
              <button
                disabled={pending}
                onClick={() => setConfirming(false)}
                className={`${btnGhost} ml-auto`}
              >
                Cancel
              </button>
              <button
                disabled={pending}
                onClick={() => void remove()}
                className={`${btnPrimary} bg-red-700 hover:bg-red-800`}
              >
                Delete Meeting
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setConfirming(true)}
                className={`${btnGhost} text-red-700`}
              >
                Delete
              </button>
              <button onClick={onView} className={`${btnGhost} ml-auto`}>
                View Meeting
              </button>
              <button onClick={onEdit} className={btnPrimary}>
                Edit Meeting
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}

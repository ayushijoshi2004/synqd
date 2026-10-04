import { useState, type FormEvent } from "react"
import type { MeetingFields, Participant } from "../../types/meeting"
import { participants as demoParticipants } from "../../mocks/participants"
import { demoConfig } from "../../config/demo"
import { dateValue } from "../../utils/meetings"
import { parseParticipants } from "../../utils/calendarParticipants"
import { validateMeetingForm } from "../../utils/meetingForm"
import Modal from "../Modal"
import { btnGhost, btnPrimary } from "../ui"

const fieldClass =
  "w-full rounded-lg border border-line bg-white px-3 py-2 text-[13px] outline-none focus:border-accent"
interface Props {
  title: string
  submitLabel: string
  initial?: MeetingFields
  allowIncomplete?: boolean
  calendarNotice?: string
  onSubmit: (meeting: MeetingFields) => Promise<unknown>
  onClose: () => void
}

export default function MeetingFormModal({
  title,
  submitLabel,
  initial,
  allowIncomplete = false,
  calendarNotice,
  onSubmit,
  onClose,
}: Props) {
  const [fields, setFields] = useState<MeetingFields>(
    initial ?? {
      title: "",
      date: dateValue(new Date()),
      startTime: "",
      endTime: "",
      participants: [],
      agenda: "",
      project: "",
      team: "",
    },
  )
  const [names, setNames] = useState(
    initial?.participants.map((person) => person.email ? `${person.name} <${person.email}>` : person.name).join(", ") ?? "",
  )
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  const enteredNames = names
    .split(/[,;\n]/)
    .map((name) => name.trim())
    .filter(Boolean)
  function change(key: keyof MeetingFields, value: string) {
    setFields((current) => ({ ...current, [key]: value }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (pending) return
    setError("")
    const known = [
      ...(initial?.participants ?? []),
      ...Object.values(demoParticipants),
    ]
    try {
      const participants: Participant[] = parseParticipants(names, known)
      const values = { ...fields, participants }
      validateMeetingForm(values, allowIncomplete)
      setPending(true)
      await onSubmit(values)
      onClose()
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to save this meeting.",
      )
      setPending(false)
    }
  }
  return (
    <Modal
      title={title}
      onClose={() => {
        if (!pending) onClose()
      }}
    >
      <form onSubmit={(event) => void submit(event)} className="p-5 space-y-4">
        <label className="block text-[13px] font-medium">
          Title <span className="text-mute">*</span>
          <input
            autoFocus
            required
            value={fields.title}
            onChange={(event) => change("title", event.target.value)}
            className={`${fieldClass} mt-1`}
          />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <label className="block text-[13px] font-medium">
            Date {allowIncomplete ? "(optional until approval)" : "*"}
            <input
              type="date"
              required={!allowIncomplete}
              value={fields.date}
              onChange={(event) => change("date", event.target.value)}
              className={`${fieldClass} mt-1`}
            />
          </label>
          <label className="block text-[13px] font-medium">
            Start time {allowIncomplete ? "(optional until approval)" : "*"}
            <input
              type="time"
              required={!allowIncomplete}
              value={fields.startTime}
              onChange={(event) => change("startTime", event.target.value)}
              className={`${fieldClass} mt-1`}
            />
          </label>
          <label className="block text-[13px] font-medium">
            End time {allowIncomplete ? "(optional until approval)" : "*"}
            <input
              type="time"
              required={!allowIncomplete}
              value={fields.endTime}
              onChange={(event) => change("endTime", event.target.value)}
              className={`${fieldClass} mt-1`}
            />
          </label>
        </div>
        <label className="block text-[13px] font-medium">
          Participants {allowIncomplete ? "(optional until approval)" : "*"}
          <textarea
            required={!allowIncomplete}
            rows={2}
            value={names}
            onChange={(event) => setNames(event.target.value)}
            placeholder="Maya Chen, Alex Rivera"
            aria-describedby="participant-help"
            className={`${fieldClass} mt-1 resize-y`}
          />
        </label>
        <p id="participant-help" className="text-[12px] text-mute -mt-2">
          Separate names with commas or new lines. For Google invitations, use Name &lt;email@example.com&gt;. {enteredNames.length}/
          {demoConfig.maxParticipants} participants in this demo.
        </p>
        {calendarNotice && <p className="text-[12px] text-mute">{calendarNotice}</p>}
        <label className="block text-[13px] font-medium">
          Agenda <span className="text-mute font-normal">(optional)</span>
          <textarea
            rows={3}
            value={fields.agenda}
            onChange={(event) => change("agenda", event.target.value)}
            className={`${fieldClass} mt-1 resize-y`}
          />
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block text-[13px] font-medium">
            Project <span className="text-mute font-normal">(optional)</span>
            <input
              value={fields.project}
              onChange={(event) => change("project", event.target.value)}
              className={`${fieldClass} mt-1`}
            />
          </label>
          <label className="block text-[13px] font-medium">
            Team <span className="text-mute font-normal">(optional)</span>
            <input
              value={fields.team}
              onChange={(event) => change("team", event.target.value)}
              className={`${fieldClass} mt-1`}
            />
          </label>
        </div>
        {error && (
          <p role="alert" className="text-[13px] text-red-700">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <button
            type="button"
            disabled={pending}
            onClick={onClose}
            className={btnGhost}
          >
            Cancel
          </button>
          <button type="submit" disabled={pending} className={btnPrimary}>
            {pending ? "Saving…" : submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  )
}

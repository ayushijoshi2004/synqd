import type {
  AIProcessingStatus,
  MeetingStatus,
  MeetingFields,
} from "../types/meeting"

export const meetingStatusLabels: Record<MeetingStatus, string> = {
  scheduled: "Scheduled",
  in_progress: "In progress",
  ended: "Ended",
  cancelled: "Cancelled",
}

export const aiStatusLabels: Record<AIProcessingStatus, string> = {
  unprocessed: "AI: Unprocessed",
  processing: "AI: Processing",
  processed: "AI: Processed",
  failed: "AI: Failed",
}

// Dates and times are local calendar values, never parsed as UTC dates.
export function localDate(value: string): Date {
  return new Date(`${value}T12:00:00`)
}

export function dateValue(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

export function formatDate(date: string): string {
  return localDate(date).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

export function timeMinutes(time: string): number {
  const [hours, minutes] = time.split(":").map(Number)
  return hours * 60 + minutes
}

export function durationMinutes(
  meeting: Pick<MeetingFields, "startTime" | "endTime">,
): number {
  return timeMinutes(meeting.endTime) - timeMinutes(meeting.startTime)
}

export function formatTime(time: string): string {
  const minutes = timeMinutes(time)
  const hours = Math.floor(minutes / 60)
  return `${hours % 12 || 12}:${String(minutes % 60).padStart(2, "0")} ${
    hours < 12 ? "AM" : "PM"
  }`
}

export function formatTimeRange(
  meeting: Pick<MeetingFields, "startTime" | "endTime">,
): string {
  return `${formatTime(meeting.startTime)} – ${formatTime(meeting.endTime)}`
}

// Structural validation is shared by local mutations. Participant limits are
// applied only in the form, so future integrations can support larger meetings.
export function validateMeeting(fields: MeetingFields, allowIncomplete = false): void {
  if (!fields.title.trim()) throw new Error("Enter a meeting title.")
  if (
    (fields.date || !allowIncomplete) && (!/^\d{4}-\d{2}-\d{2}$/.test(fields.date) ||
    Number.isNaN(localDate(fields.date).getTime()) ||
    dateValue(localDate(fields.date)) !== fields.date)
  ) {
    throw new Error("Choose a valid meeting date.")
  }
  if (
    ![fields.startTime, fields.endTime].every((time) =>
      (allowIncomplete && !time) || /^([01]\d|2[0-3]):[0-5]\d$/.test(time),
    )
  ) {
    throw new Error("Enter valid start and end times.")
  }
  if (fields.startTime && fields.endTime && durationMinutes(fields) <= 0)
    throw new Error("End time must be after start time on the same date.")
  if (
    (!allowIncomplete && !fields.participants.length) ||
    fields.participants.some((person) => !person.name.trim())
  ) {
    throw new Error("Add at least one participant.")
  }
  const names = fields.participants.map((person) =>
    person.name.trim().toLowerCase(),
  )
  if (new Set(names).size !== names.length)
    throw new Error("Remove duplicate participants.")
}

// Only http(s) links from stored data are rendered as hrefs.
export function safeHttpUrl(value?: string): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.href
      : undefined
  } catch {
    return undefined
  }
}

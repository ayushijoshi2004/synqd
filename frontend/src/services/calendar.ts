import { calendarProjects } from "../mocks/calendar"
import { participants } from "../mocks/participants"
import { config } from "../config/env"
const API_BASE_URL = config.apiBaseUrl
import type {
  CalendarData,
  CalendarEvent,
  FollowUpMeeting,
} from "../types/calendar"
import type { Meeting, MeetingFields } from "../types/meeting"
import { addDays, weekOf } from "../utils/calendar"
import {
  durationMinutes,
  localDate,
  timeMinutes,
  validateMeeting,
} from "../utils/meetings"
import {
  applyFollowUpResponse,
  getMeeting,
  getMeetingsSnapshot,
  subscribeMeetings,
} from "./meetings"

let proposals: FollowUpMeeting[] = []
// Only review edits are local. Persisted proposals always come from meetings.
const drafts = new Map<string, MeetingFields>()
const listeners = new Set<() => void>()
export const getFollowUpsSnapshot = () => proposals
export function subscribeFollowUps(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
function publish(next: FollowUpMeeting[]) {
  proposals = next
  listeners.forEach((listener) => listener())
}

function hydrateFollowUps() {
  const backendProposals = getMeetingsSnapshot().meetings.flatMap(
    (meeting) => meeting.followUps ?? [],
  )
  const suggestedIds = new Set(
    backendProposals.filter((item) => item.status === "suggested").map((item) => item.id),
  )
  for (const id of drafts.keys())
    if (!suggestedIds.has(id)) drafts.delete(id)
  publish(backendProposals.map((proposal) => ({
    ...structuredClone(proposal),
    ...drafts.get(proposal.id),
  })))
}
subscribeMeetings(hydrateFollowUps)
hydrateFollowUps()

// Calendar events are projections of the meetings service, never another store.
export function getCalendarView(startDate: string): CalendarData {
  const week = weekOf(startDate)
  const dates = Array.from({ length: 7 }, (_, day) => addDays(week, day))
  const allRecords = [
    ...getMeetingsSnapshot().meetings.map((meeting) => ({
      ...meeting,
      kind: "event" as const,
    })),
    ...proposals
      .filter((proposal) => proposal.status === "suggested" && proposal.date && proposal.startTime && proposal.endTime)
      .map((proposal) => ({ ...proposal, kind: "proposed" as const })),
  ]
  const events: CalendarEvent[] = allRecords
    .filter((record) => dates.includes(record.date))
    .map((record) => ({
      id: record.id,
      day: dates.indexOf(record.date),
      date: record.date,
      title: record.title,
      project: record.project || "No project",
      kind: record.kind,
      startHour: timeMinutes(record.startTime) / 60,
      durationHours: durationMinutes(record) / 60,
    }))
  // Keep the original workweek grid; include weekend columns when needed.
  const dayCount = events.some((event) => event.day > 4) ? 7 : 5
  const firstHour = Math.min(
    9,
    ...events.map((event) => Math.floor(event.startHour)),
  )
  const lastHour = Math.max(
    17,
    ...events.map((event) => Math.ceil(event.startHour + event.durationHours)),
  )
  const projectNames = new Set([
    ...calendarProjects.map((project) => project.name),
    ...allRecords.map((record) => record.project || "No project"),
  ])
  const projects = [...projectNames].map(
    (name) =>
      calendarProjects.find((project) => project.name === name) ?? {
        name,
        color: "#2f6f5e",
      },
  )
  return {
    events,
    projects,
    days: dates
      .slice(0, dayCount)
      .map((date) =>
        localDate(date).toLocaleDateString("en-US", {
          weekday: "short",
          day: "numeric",
        }),
      ),
    hours: Array.from(
      { length: lastHour - firstHour },
      (_, index) => firstHour + index,
    ),
    rangeLabel: `${localDate(week).toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${localDate(dates[dayCount - 1]).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`,
  }
}
export async function getCalendar(): Promise<CalendarData> {
  return getCalendarView(getMeetingsSnapshot().focusDate)
}

// Canned generation only; save the suggestion inside an existing source meeting.
export async function proposeFollowUp(
  request: string,
  week: string,
): Promise<FollowUpMeeting> {
  if (!request.trim()) throw new Error("Describe the follow-up first.")
  const sourceId = getMeetingsSnapshot().meetings.find(
    (meeting) => meeting.project === "Atlas Launch",
  )?.id ?? getMeetingsSnapshot().meetings[0]?.id
  if (!sourceId) throw new Error("Create a source meeting before suggesting a follow-up.")
  const source = await getMeeting(sourceId)
  if (!source) throw new Error("The source meeting no longer exists.")
  const proposal: FollowUpMeeting = {
    id: crypto.randomUUID(),
    status: "suggested",
    sourceMeetingId: source.id,
    title: "Design team follow-up",
    date: addDays(weekOf(week), 3),
    startTime: "13:00",
    endTime: "14:00",
    project: "Atlas Launch",
    team: "Design",
    agenda: request.trim(),
    participants: [participants.maya, participants.alex, participants.priya],
  }
  // Read current backend follow-ups, never replace them with frontend mocks.
  const response = await fetch(`${API_BASE_URL}/meetings/${encodeURIComponent(source.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ followUps: [...(source.followUps ?? []), proposal] }),
  })
  if (!response.ok)
    throw new Error(`Failed to save follow-up: ${response.status}`)
  const updatedSource: Meeting = await response.json()
  applyFollowUpResponse(updatedSource)
  return structuredClone(proposal)
}
function suggested(id: string): FollowUpMeeting {
  const proposal = proposals.find((item) => item.id === id)
  if (!proposal || proposal.status !== "suggested")
    throw new Error("This suggestion is no longer awaiting approval.")
  return proposal
}
function fieldsOnly(fields: MeetingFields, allowIncomplete = false): MeetingFields {
  validateMeeting(fields, allowIncomplete)
  return structuredClone({
    title: fields.title.trim(),
    date: fields.date,
    startTime: fields.startTime,
    endTime: fields.endTime,
    agenda: fields.agenda.trim(),
    project: fields.project.trim(),
    team: fields.team.trim(),
    participants: fields.participants,
  })
}
export async function editFollowUp(
  id: string,
  fields: MeetingFields,
): Promise<void> {
  suggested(id)
  if (resolving.has(id)) throw new Error("This suggestion is being updated.")
  const values = fieldsOnly(fields, true)
  drafts.set(id, values)
  hydrateFollowUps()
}
const resolving = new Set<string>()
export async function approveFollowUp(
  id: string,
  fields: MeetingFields,
): Promise<string> {
  const proposal = suggested(id)
  if (resolving.has(id))
    throw new Error("This suggestion is already being updated.")
  resolving.add(id)
  try {
    const values = fieldsOnly(fields)
    const response = await fetch(followUpUrl(proposal, "approve"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    })
    if (!response.ok)
      throw new Error(`Failed to approve follow-up: ${response.status}`)
    const { sourceMeeting, meeting }: { sourceMeeting: Meeting; meeting: Meeting } =
      await response.json()
    applyFollowUpResponse(sourceMeeting, meeting)
    return meeting.id
  } finally {
    resolving.delete(id)
  }
}
export async function dismissFollowUp(id: string): Promise<void> {
  const proposal = suggested(id)
  if (resolving.has(id)) throw new Error("This suggestion is being updated.")
  resolving.add(id)
  try {
    const response = await fetch(followUpUrl(proposal, "dismiss"), { method: "POST" })
    if (!response.ok)
      throw new Error(`Failed to dismiss follow-up: ${response.status}`)
    const sourceMeeting: Meeting = await response.json()
    applyFollowUpResponse(sourceMeeting)
  } finally {
    resolving.delete(id)
  }
}

function followUpUrl(proposal: FollowUpMeeting, action: "approve" | "dismiss") {
  return `${API_BASE_URL}/meetings/${encodeURIComponent(proposal.sourceMeetingId)}/follow-ups/${encodeURIComponent(proposal.id)}/${action}`
}

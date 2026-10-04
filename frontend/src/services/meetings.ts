import {
  meetings,
  meetingProjects,
  sharedMeetingDetail,
} from "../mocks/meetings"
import { config } from "../config/env"
import type {
  ActionItem,
  ActionItemStatus,
  AgendaItem,
  Meeting,
  MeetingDetail,
  MeetingFields,
  MeetingProject,
  ProjectOverview,
} from "../types/meeting"
import { validateMeeting } from "../utils/meetings"
const API_BASE_URL = config.apiBaseUrl;
// Shared frontend snapshot of backend meetings and existing local demo details.
// Calendar projects server-owned followUps from this same snapshot.
function agendaEntries(
  agenda: string,
  previous: AgendaItem[] = [],
): AgendaItem[] {
  return agenda
    .split("\n")
    .map((title) => title.trim())
    .filter(Boolean)
    .map(
      (title) =>
        previous.find((entry) => entry.title === title) ?? {
          title,
          timestamp: "",
          completed: false,
        },
    )
}

function projectOverview(
  project: string,
  storedJiraProjectUrl?: string,
): ProjectOverview {
  const metadata = meetingProjects.find((item) => item.name === project)
  const jiraProjectUrl = storedJiraProjectUrl || metadata?.jiraProjectUrl
  if (project === sharedMeetingDetail.projectOverview.name) {
    return {
      ...structuredClone(sharedMeetingDetail.projectOverview),
      jiraProjectUrl,
    }
  }
  return {
    name: project || "No project",
    description: "",
    previousLaunchDate: "",
    launchDate: "",
    resources: [],
    additionalResourceCount: 0,
    previousMeetingCount: 0,
    relatedResources: [],
    jiraProjectUrl,
  }
}

function withDetail(meeting: Meeting): MeetingDetail {
  // Persisted detail always wins. Missing intelligence stays empty, never mock.
  const stored = meeting as Partial<MeetingDetail>
  return {
    ...structuredClone(meeting),
    agendaEntries: structuredClone(stored.agendaEntries ?? agendaEntries(meeting.agenda)),
    summary: structuredClone(stored.summary ?? {
      beforeHighlight: "", highlight: "", afterHighlight: "", points: [],
    }),
    transcript: structuredClone(stored.transcript ?? []),
    decisions: structuredClone(stored.decisions ?? []),
    actionItems: structuredClone(stored.actionItems ?? []),
    unresolvedItems: structuredClone(stored.unresolvedItems ?? []),
    projectOverview: structuredClone(stored.projectOverview ?? projectOverview(meeting.project)),
    assistant: structuredClone(stored.assistant ?? { scopeLabel: "Meeting", suggestions: [] }),
  }
}

let snapshot = {
  meetings: meetings.map(withDetail),
  focusDate:
    meetings.find((meeting) => meeting.status === "scheduled")?.date ??
    meetings[0].date,
}
const listeners = new Set<() => void>()
let revision = 0
export const getMeetingsSnapshot = () => snapshot
export function subscribeMeetings(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
function publish(
  nextMeetings: MeetingDetail[],
  focusDate = snapshot.focusDate,
): void {
  revision++
  snapshot = { meetings: nextMeetings, focusDate }
  listeners.forEach((listener) => listener())
}

export async function getMeetings(): Promise<Meeting[]> {
  const requestedRevision = revision
  const response = await fetch(`${API_BASE_URL}/meetings`)

  if (!response.ok) {
    throw new Error(`Failed to load meetings: ${response.status}`)
  }

  const backendMeetings: Meeting[] = await response.json()
  // A load started before a mutation must not resurrect its old suggestions.
  if (requestedRevision !== revision)
    return structuredClone(snapshot.meetings)
  const detailedMeetings = backendMeetings.map(withDetail)

  publish(detailedMeetings)

  return structuredClone(detailedMeetings)
}

// Commit server-owned follow-up state and its scheduled meeting together.
// Preserve existing local detail/task behavior when only followUps changed.
export function applyFollowUpResponse(
  sourceMeeting: Meeting,
  scheduledMeeting?: Meeting,
): void {
  const current = snapshot.meetings.find((item) => item.id === sourceMeeting.id)
  const source = current
    ? { ...current, followUps: structuredClone(sourceMeeting.followUps ?? []) }
    : withDetail(sourceMeeting)
  const updates = new Map<string, MeetingDetail>([[source.id, source]])
  if (scheduledMeeting)
    updates.set(scheduledMeeting.id, withDetail(scheduledMeeting))
  const next = snapshot.meetings.map((item) => updates.get(item.id) ?? item)
  for (const [id, meeting] of updates)
    if (!snapshot.meetings.some((item) => item.id === id)) next.push(meeting)
  publish(next, scheduledMeeting?.date ?? snapshot.focusDate)
}
export async function getMeeting(id: string): Promise<MeetingDetail | null> {
  const response = await fetch(`${API_BASE_URL}/meetings/${id}`, { cache: "no-store" })

  if (response.status === 404) {
    return null
  }

  if (!response.ok) {
    throw new Error(`Failed to load meeting: ${response.status}`)
  }

  const meeting: Meeting = await response.json()

  return structuredClone(withDetail(meeting))
}

export function applyMeetingResponse(meeting: MeetingDetail): void {
  publish(snapshot.meetings.map((current) => {
    if (current.id !== meeting.id) return current
    return {
      ...meeting,
      // A Jira response may arrive while the processing response is in flight.
      actionItems: meeting.actionItems.map((task) => {
        const local = current.actionItems.find((item) => item.id === task.id)
        return !task.jiraIssueKey && local?.jiraIssueKey
          ? { ...task, jiraIssueKey: local.jiraIssueKey, jiraIssueUrl: local.jiraIssueUrl }
          : task
      }),
    }
  }))
}

export async function refreshMeeting(id: string): Promise<void> {
  const requestedRevision = revision
  const meeting = await getMeeting(id)
  if (meeting && requestedRevision === revision) applyMeetingResponse(meeting)
}

const processingRequests = new Set<string>()
export async function processMeeting(id: string): Promise<void> {
  const current = snapshot.meetings.find((meeting) => meeting.id === id)
  if (!current) throw new Error("Meeting not found.")
  if (processingRequests.has(id)) throw new Error("This meeting is already being processed.")
  processingRequests.add(id)
  publish(snapshot.meetings.map((meeting) =>
    meeting.id === id ? { ...meeting, aiStatus: "processing" } : meeting,
  ))
  try {
    const response = await fetch(`${API_BASE_URL}/meetings/${encodeURIComponent(id)}/process`, { method: "POST" })
    if (!response.ok) throw new Error(`Processing failed: ${response.status}`)
    const stored: Meeting = await response.json()
    applyMeetingResponse(withDetail(stored))
  } catch {
    try {
      await refreshMeeting(id)
    } catch {
      // Keep saved content; a network failure cannot invent persisted results.
      publish(snapshot.meetings.map((meeting) =>
        meeting.id === id ? { ...meeting, aiStatus: current.aiStatus } : meeting,
      ))
    }
    throw new Error("AI processing unavailable. Your meeting and transcript are still saved.")
  } finally {
    processingRequests.delete(id)
  }
}
export function getProjectGroups(): MeetingProject[] {
  const names = new Set([
    ...meetingProjects.map((project) => project.name),
    ...snapshot.meetings.map((meeting) => meeting.project),
  ])
  return [...names].map((name) => {
    const metadata = meetingProjects.find((project) => project.name === name)
    const tasks = snapshot.meetings
      .filter((meeting) => meeting.project === name)
      .flatMap((meeting) => meeting.actionItems)
    return {
      ...metadata,
      name,
      memory: metadata?.memory ?? "",
      openActionItems: tasks.filter((task) => task.status !== "done").length,
    }
  })
}
export async function getMeetingProjects(): Promise<MeetingProject[]> {
  return structuredClone(getProjectGroups())
}

function cleanFields(fields: MeetingFields): MeetingFields {
  validateMeeting(fields)
  return structuredClone({
    title: fields.title.trim(),
    date: fields.date,
    startTime: fields.startTime,
    endTime: fields.endTime,
    participants: fields.participants.map((person) => ({
      ...person,
      name: person.name.trim(),
    })),
    project: fields.project.trim(),
    team: fields.team.trim(),
    agenda: fields.agenda.trim(),
  })
}
export async function createMeeting(
    fields: MeetingFields,
): Promise<MeetingDetail> {
  const values = cleanFields(fields)

  const response = await fetch(`${API_BASE_URL}/meetings`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...values,
      agendaEntries: agendaEntries(values.agenda),
      status: "scheduled",
      aiStatus: "unprocessed",
      preview: "",
    }),
  })

  if (!response.ok) {
    throw new Error(`Failed to create meeting: ${response.status}`)
  }

  const created: Meeting = await response.json()
  const meeting = withDetail(created)

  publish([...snapshot.meetings, meeting], meeting.date)

  return structuredClone(meeting)
}
export async function updateMeeting(
    id: string,
    fields: MeetingFields,
): Promise<MeetingDetail> {
  const current = snapshot.meetings.find((meeting) => meeting.id === id)
  if (!current) throw new Error("Meeting not found.")

  const values = cleanFields(fields)
  const nextAgenda = values.agenda === current.agenda
    ? current.agendaEntries
    : agendaEntries(values.agenda, current.agendaEntries)

  const response = await fetch(`${API_BASE_URL}/meetings/${id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...values, agendaEntries: nextAgenda }),
  })

  if (!response.ok) {
    throw new Error(`Failed to update meeting: ${response.status}`)
  }

  const updated: Meeting = await response.json()

  const next: MeetingDetail = {
    ...current,
    ...updated,
    agendaEntries: structuredClone((updated as Partial<MeetingDetail>).agendaEntries ?? nextAgenda),
    projectOverview: projectOverview(
      updated.project,
      (updated as Partial<MeetingDetail>).projectOverview?.jiraProjectUrl ??
        current.projectOverview.jiraProjectUrl,
    ),
  }

  publish(
      snapshot.meetings.map((meeting) =>
          meeting.id === id ? next : meeting
      ),
      next.date,
  )

  return structuredClone(next)
}
export async function deleteMeeting(id: string): Promise<void> {
  if (!snapshot.meetings.some((meeting) => meeting.id === id))
    throw new Error("Meeting not found.")

  const response = await fetch(`${API_BASE_URL}/meetings/${id}`, {
    method: "DELETE",
  })

  if (!response.ok) {
    throw new Error(`Failed to delete meeting: ${response.status}`)
  }

  publish(snapshot.meetings.filter((meeting) => meeting.id !== id))
}

export async function updateActionItemStatus(
  meetingId: string,
  itemId: string,
  status: ActionItemStatus,
): Promise<void> {
  if (!["todo", "in_progress", "done"].includes(status))
    throw new Error("Unknown task status.")
  const meeting = snapshot.meetings.find((item) => item.id === meetingId)
  if (!meeting?.actionItems.some((item) => item.id === itemId))
    throw new Error("Action item not found.")
  publish(
    snapshot.meetings.map((item) =>
      item.id === meetingId
        ? {
            ...item,
            actionItems: item.actionItems.map((task) =>
              task.id === itemId ? { ...task, status } : task,
            ),
          }
        : item,
    ),
  )
}

const jiraRequestsInFlight = new Set<string>()

export async function createJiraTickets(
  meetingId: string,
  actionItemIds: string[],
): Promise<void> {
  const meeting = snapshot.meetings.find((item) => item.id === meetingId)

  if (!meeting) {
    throw new Error("Meeting not found.")
  }

  // The backend is authoritative; this only avoids sending obvious repeats.
  const idsToCreate = [...new Set(actionItemIds)].filter((actionItemId) => {
    const task = meeting.actionItems.find((item) => item.id === actionItemId)
    return (
      task &&
      !task.jiraIssueKey &&
      !jiraRequestsInFlight.has(`${meetingId}:${actionItemId}`)
    )
  })

  const results = await Promise.allSettled(
    idsToCreate.map(async (actionItemId) => {
      const key = `${meetingId}:${actionItemId}`
      jiraRequestsInFlight.add(key)
      try {
        const response = await fetch(
          `${API_BASE_URL}/meetings/${meetingId}/action-items/${actionItemId}/jira`,
          { method: "POST" },
        )

        if (!response.ok) {
          throw new Error(`Failed to create Jira ticket: ${response.status}`)
        }

        return (await response.json()) as ActionItem
      } finally {
        jiraRequestsInFlight.delete(key)
      }
    }),
  )

  // Keep every ticket that was created, even if another one failed.
  const updates = results.flatMap((result) =>
    result.status === "fulfilled" && result.value.jiraIssueKey
      ? [result.value]
      : [],
  )

  if (updates.length) {
    publish(
      snapshot.meetings.map((item) =>
        item.id === meetingId
          ? {
              ...item,
              actionItems: item.actionItems.map((task) => {
                const updated = updates.find((result) => result.id === task.id)

                // Only Jira fields change; status and other edits are kept.
                return updated
                  ? {
                      ...task,
                      jiraIssueKey: updated.jiraIssueKey,
                      jiraIssueUrl: updated.jiraIssueUrl,
                    }
                  : task
              }),
            }
          : item,
      ),
    )
  }

  const failed = results.find((result) => result.status === "rejected")
  if (failed?.status === "rejected") throw failed.reason
}

export const normalizeMeetingResponse = withDetail

export interface Participant {
  id: string
  name: string
  color: string
  email?: string
}

export type MeetingStatus = "scheduled" | "in_progress" | "ended" | "cancelled"
export type AIProcessingStatus = "unprocessed" | "processing" | "processed" | "failed"
export type ActionItemStatus = "todo" | "in_progress" | "done"

export interface MeetingFields {
  title: string
  // Local ISO date (YYYY-MM-DD) and 24-hour times (HH:mm).
  date: string
  startTime: string
  endTime: string
  project: string
  team: string
  participants: Participant[]
  agenda: string
}

export type FollowUpStatus = "suggested" | "approved" | "dismissed"
export interface FollowUpMeeting extends MeetingFields {
  // Suggested/dismissed records may have empty date/time strings and no attendees.
  // Approval still requires the complete MeetingFields form.
  id: string
  status: FollowUpStatus
  sourceMeetingId: string
  scheduledMeetingId?: string
}

export interface GoogleCalendarState {
  status: "not_connected" | "pending" | "failed" | "created"
  accountId?: string
  timeZone?: string
  eventId?: string
  eventUrl?: string
  error?: string
}

export interface Meeting extends MeetingFields {
  id: string
  status: MeetingStatus
  aiStatus: AIProcessingStatus
  preview: string
  followUps?: FollowUpMeeting[]
  googleCalendar?: GoogleCalendarState
  googleMeetUrl?: string
  transcription?: TranscriptionState
}

// Metadata for grouping meetings, not a separate project destination.
export interface MeetingProject {
  name: string
  memory: string
  openActionItems: number
  jiraProjectUrl?: string
}

export interface TranscriptEntry {
  timestamp: string
  speaker: Participant
  text: string
}

export interface Decision {
  id: string
  text: string
  participant: Participant | null
  timestamp: string
  note: string
}

export interface ActionItem {
  id: string
  text: string
  assignee: Participant | null
  due: string
  status: ActionItemStatus
  jiraIssueKey?: string
  jiraIssueUrl?: string
}

export interface AgendaItem {
  title: string
  timestamp: string
  completed: boolean
}

export interface MeetingSummary {
  beforeHighlight: string
  highlight: string
  afterHighlight: string
  points: string[]
}

export interface ProjectOverview {
  name: string
  description: string
  previousLaunchDate: string
  launchDate: string
  jiraProjectUrl?: string
  resources: string[]
  additionalResourceCount: number
  previousMeetingCount: number
  relatedResources: string[]
}

export interface AssistantContext {
  scopeLabel: string
  suggestions: string[]
}

export interface AssistantAnswer {
  text: string
  sources: string[]
}

export interface AssistantMessage {
  question: string
  answer?: AssistantAnswer
}

export interface MeetingDetail extends Meeting {
  unresolvedItems?: string[]
  agendaEntries: AgendaItem[]
  summary: MeetingSummary
  transcript: TranscriptEntry[]
  decisions: Decision[]
  actionItems: ActionItem[]
  projectOverview: ProjectOverview
  assistant: AssistantContext
}

export interface TranscriptionState {
  id: string
  status: "starting" | "transcribing" | "stopping" | "completed" | "error"
  botId?: number
  attempted?: boolean
  polling?: boolean
  terminal?: boolean
  error?: string
}

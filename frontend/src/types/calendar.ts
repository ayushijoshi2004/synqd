export type { FollowUpMeeting, FollowUpStatus } from "./meeting"

export type CalendarEventKind = "event" | "proposed"
export interface CalendarEvent {
  id: string
  day: number
  date: string
  startHour: number
  durationHours: number
  title: string
  project: string
  kind: CalendarEventKind
}
export interface CalendarProject {
  name: string
  color: string
}
export interface CalendarData {
  events: CalendarEvent[]
  projects: CalendarProject[]
  days: string[]
  hours: number[]
  rangeLabel: string
}

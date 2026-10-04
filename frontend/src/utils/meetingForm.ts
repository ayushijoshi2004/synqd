import { demoConfig } from "../config/demo"
import type { MeetingFields } from "../types/meeting"
import { validateMeeting } from "./meetings"

export function validateMeetingForm(fields: MeetingFields, allowIncomplete = false): void {
  validateMeeting(fields, allowIncomplete)
  if (fields.participants.length > demoConfig.maxParticipants) {
    throw new Error(
      `This demo supports up to ${demoConfig.maxParticipants} participants. Remove ${fields.participants.length - demoConfig.maxParticipants} to continue.`,
    )
  }
}

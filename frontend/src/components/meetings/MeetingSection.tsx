import type { Meeting } from "../../types/meeting"
import MeetingCard from "./MeetingCard"

interface MeetingSectionProps {
  title: string
  subtitle: string
  meetings: Meeting[]
  onOpenMeeting: (id: string) => void
}

export default function MeetingSection({
  title,
  subtitle,
  meetings,
  onOpenMeeting,
}: MeetingSectionProps) {
  if (!meetings.length) return null
  return (
    <div className="mb-10">
      <div className="flex items-baseline gap-3 mb-4">
        <h2 className="font-semibold text-[17px] tracking-tight">{title}</h2>
        <span className="text-[12px] text-mute">{subtitle}</span>
      </div>
      <div className="grid gap-4 grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {meetings.map((meeting) => (
          <MeetingCard
            key={meeting.id}
            meeting={meeting}
            onOpen={() => onOpenMeeting(meeting.id)}
          />
        ))}
      </div>
    </div>
  )
}

import { Clock, Sparkles } from "lucide-react"
import type { Meeting } from "../../types/meeting"
import { AvatarStack, Pill } from "../ui"
import {
  aiStatusLabels,
  formatDate,
  formatTimeRange,
  meetingStatusLabels,
} from "../../utils/meetings"

export default function MeetingCard({
  meeting,
  onOpen,
}: {
  meeting: Meeting
  onOpen: () => void
}) {
  return (
    <button
      onClick={onOpen}
      className="text-left bg-card border border-line rounded-2xl p-5 flex flex-col gap-3 hover:border-accent/40 hover:shadow-[0_6px_20px_rgba(20,25,22,0.06)] transition-all"
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-mute flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-accent" />{" "}
          {meeting.project || "No project"}
        </span>
        <Pill tone={meeting.status}>{meetingStatusLabels[meeting.status]}</Pill>
      </div>
      <div>
        <h3 className="font-semibold text-[15px] tracking-tight">
          {meeting.title}
        </h3>
        <p className="text-[12px] text-mute mt-1 flex items-center gap-1.5 font-mono">
          <Clock size={12} /> {formatDate(meeting.date)} ·{" "}
          {formatTimeRange(meeting)}
        </p>
      </div>
      <div className="rounded-xl bg-accent-soft/60 px-3 py-2.5 text-[12.5px] leading-relaxed text-[#23453b]">
        <div className="flex items-center gap-1 text-[10.5px] uppercase tracking-wider font-semibold text-accent mb-1">
          <Sparkles size={11} /> {aiStatusLabels[meeting.aiStatus]}
        </div>
        {meeting.preview || meeting.agenda || "No AI results yet."}
      </div>
      <div className="flex items-center justify-between mt-auto pt-1">
        <AvatarStack participants={meeting.participants} />
        <span className="text-[11px] text-mute">{meeting.team}</span>
      </div>
    </button>
  )
}

import { FileText, Sparkles } from "lucide-react"
import type { MeetingDetail } from "../../types/meeting"
import type { MeetingDetailTab } from "../../types/navigation"
import { Avatar, Card } from "../ui"
import MeetingAssistant from "./MeetingAssistant"

const tabs = [
  ["summary", "Summary", Sparkles],
  ["transcript", "Transcript", FileText],
  ["ai", "AI Assistant", Sparkles],
] as const

interface MeetingContentProps {
  meeting: MeetingDetail
  tab: MeetingDetailTab
  onTabChange: (tab: MeetingDetailTab) => void
  highlightedTimestamp: string | null
  onTranscriptSelect: (timestamp: string) => void
}

export default function MeetingContent({
  meeting,
  tab,
  onTabChange,
  highlightedTimestamp,
  onTranscriptSelect,
}: MeetingContentProps) {
  const { summary } = meeting
  const transcript = meeting.transcript
  return (
    <Card className="xl:flex-1 xl:min-h-0 flex flex-col">
      <div className="flex items-center gap-1 px-3 pt-2 shrink-0 border-b border-line">
        {tabs.map(([k, l, Icon]) => (
          <button
            key={k}
            onClick={() => onTabChange(k)}
            className={`flex items-center gap-1.5 h-9 px-3 text-[13px] font-medium border-b-2 -mb-px transition-colors ${
              tab === k
                ? "border-accent text-ink"
                : "border-transparent text-mute hover:text-ink"
            }`}
          >
            <Icon size={14} className={tab === k ? "text-accent" : ""} /> {l}
          </button>
        ))}
      </div>

      {tab === "summary" && (
        <div className="p-5 xl:overflow-auto">
          <p className="text-[17px] leading-snug tracking-tight font-medium">
            {!summary.beforeHighlight && !summary.highlight && !summary.afterHighlight && "No summary available yet."}
            {summary.beforeHighlight}
            <span className="text-accent">{summary.highlight}</span>
            {summary.afterHighlight}
          </p>
          <ul className="mt-4 grid gap-2 sm:grid-cols-3 text-[12.5px] text-[#3c403e]">
            {summary.points.map((t) => (
              <li
                key={t}
                className="rounded-xl bg-accent-soft/50 border border-line p-3 leading-relaxed"
              >
                {t}
              </li>
            ))}
          </ul>
          {!!meeting.unresolvedItems?.length && (
            <div className="mt-4 border-t border-line pt-3">
              <h3 className="text-[13px] font-semibold">Open items</h3>
              <ul className="mt-2 space-y-2 text-[13px] text-mute">
                {meeting.unresolvedItems.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {tab === "transcript" && (
        <div className="p-3 xl:flex-1 max-h-96 xl:max-h-none overflow-auto space-y-1">
          {!transcript.length && (
            <p className="p-2 text-[13px] text-mute">
              No transcript available yet.
            </p>
          )}
          {transcript.map((l, index) => (
            <button
              key={`${index}-${l.timestamp}`}
              onClick={() => onTranscriptSelect(l.timestamp)}
              className={`w-full text-left rounded-lg px-3 py-2 transition-colors ${
                highlightedTimestamp === l.timestamp
                  ? "bg-accent-soft ring-1 ring-accent/30"
                  : "hover:bg-soft"
              }`}
            >
              <div className="flex items-center gap-2 text-[11.5px]">
                <Avatar participant={l.speaker} size={18} />
                <b>{l.speaker.name}</b>
                <span className="font-mono text-mute">{l.timestamp}</span>
              </div>
              <p className="text-[13px] text-[#3c403e] mt-1 leading-relaxed">
                {l.text}
              </p>
            </button>
          ))}
        </div>
      )}

      <MeetingAssistant
        key={meeting.id}
        meetingId={meeting.id}
        active={tab === "ai"}
      />
    </Card>
  )
}

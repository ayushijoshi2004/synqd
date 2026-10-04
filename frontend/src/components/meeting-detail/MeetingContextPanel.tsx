import { ArrowRight, Check, Gavel, ListOrdered } from "lucide-react"
import type { MeetingDetail } from "../../types/meeting"
import { Avatar, Card, CardHead } from "../ui"

interface MeetingContextPanelProps {
  meeting: MeetingDetail
  onJump: (timestamp: string) => void
}

export default function MeetingContextPanel({
  meeting,
  onJump,
}: MeetingContextPanelProps) {
  const { agendaEntries, decisions, projectOverview } = meeting
  return (
    <div className="flex flex-col gap-4 order-2 xl:order-1 xl:min-h-0">
      <Card>
        <CardHead icon={<ListOrdered size={15} />} title="Agenda" />
        <ol className="px-5 pb-5 space-y-2.5">
          {!agendaEntries.length && (
            <li className="text-[13px] text-mute">No agenda added.</li>
          )}
          {agendaEntries.map(({ title, timestamp, completed }, i) => (
            <li
              key={`${title}-${i}`}
              className="flex items-center gap-2.5 text-[13px]"
            >
              <span
                className={`size-5 rounded-full flex items-center justify-center text-[10.5px] font-mono shrink-0 ${
                  completed ? "bg-accent text-white" : "bg-soft text-mute"
                }`}
              >
                {completed ? <Check size={11} /> : i + 1}
              </span>
              <span className="flex-1">{title}</span>
              {timestamp && (
                <button
                  onClick={() => onJump(timestamp)}
                  className="font-mono text-[11px] text-mute hover:text-accent"
                >
                  {timestamp}
                </button>
              )}
            </li>
          ))}
        </ol>
      </Card>
      <Card className="xl:flex-1 xl:min-h-0 flex flex-col">
        <CardHead icon={<Gavel size={15} />} title="Decisions" />
        <div className="px-4 pb-4 space-y-2.5 xl:flex-1 xl:overflow-auto">
          {!decisions.length && (
            <p className="text-[13px] text-mute">No decisions yet.</p>
          )}
          {decisions.map((d) => (
            <div key={d.id} className="rounded-xl border border-line p-3.5">
              <p className="text-[13px] font-medium leading-snug">{d.text}</p>
              <p className="text-[12px] text-mute mt-1.5 leading-relaxed">
                {d.note}
              </p>
              <div className="flex items-center gap-2 mt-2.5 text-[11.5px] text-mute">
                {d.participant && <Avatar participant={d.participant} size={18} />}{" "}
                {d.participant?.name.split(" ")[0] ?? "Unattributed"}
                {d.timestamp && (
                <button
                  onClick={() => onJump(d.timestamp)}
                  className="ml-auto font-mono text-accent bg-accent-soft rounded-md px-2 py-0.5 hover:bg-accent hover:text-white transition-colors"
                >
                  ▶ {d.timestamp}
                </button>
                )}
              </div>
            </div>
          ))}
          {meeting.id === "m1" && (
            <div className="rounded-xl bg-amber-soft text-amber-ink px-3.5 py-2.5 text-[12px] leading-relaxed">
              <b>What changed</b>
              <br />
              {`${projectOverview.previousLaunchDate} `}
              <ArrowRight size={11} className="inline mx-0.5" />
              {` ${projectOverview.launchDate}`}
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

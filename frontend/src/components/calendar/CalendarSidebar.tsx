import type {
  CalendarEvent,
  CalendarEventKind,
  CalendarProject,
} from "../../types/calendar"
import { formatHour } from "../../utils/calendar"
import { Card } from "../ui"

const eventTypes = [
  ["event", "Meetings"],
  ["proposed", "Suggested"],
] as const
const label =
  "text-[11px] uppercase tracking-wider text-mute font-medium mb-1.5"

interface CalendarSidebarProps {
  projectOptions: CalendarProject[]
  projectColors: Record<string, string>
  selectedProjects: string[]
  selectedTypes: CalendarEventKind[]
  upcoming: CalendarEvent[]
  days: string[]
  onToggleProject: (project: string) => void
  onToggleType: (type: CalendarEventKind) => void
  onSelect: (id: string) => void
}

export default function CalendarSidebar({
  projectOptions,
  projectColors,
  selectedProjects,
  selectedTypes,
  upcoming,
  days,
  onToggleProject,
  onToggleType,
  onSelect,
}: CalendarSidebarProps) {
  return (
    <div className="flex flex-col gap-3 lg:min-h-0 order-2 lg:order-1">
      <Card className="p-3.5 shrink-0 text-[13px]">
        <div className={label}>Projects</div>
        {projectOptions.map(({ name: p, color }) => (
          <label
            key={p}
            className="flex items-center gap-2.5 h-7 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={selectedProjects.includes(p)}
              onChange={() => onToggleProject(p)}
              className="size-4"
              style={{ accentColor: color }}
            />{" "}
            {p}
          </label>
        ))}
        <div className={`${label} mt-2.5`}>Type</div>
        {eventTypes.map(([v, l]) => (
          <label
            key={v}
            className="flex items-center gap-2.5 h-7 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={selectedTypes.includes(v)}
              onChange={() => onToggleType(v)}
              className="size-4 accent-[#2f6f5e]"
            />{" "}
            {l}
          </label>
        ))}
      </Card>
      <Card className="p-3.5 lg:flex-1 lg:min-h-0 lg:overflow-auto">
        <div className={label}>Upcoming</div>
        {upcoming.map((e) => (
          <button
            key={e.id}
            onClick={() => onSelect(e.id)}
            className="w-full text-left flex items-center gap-2.5 py-1.5 text-[12.5px] hover:bg-soft rounded-lg px-1"
          >
            <span
              className="w-1 h-7 rounded-full"
              style={{ background: projectColors[e.project] }}
            />
            <div>
              <div className="font-medium">{e.title}</div>
              <div className="text-mute font-mono text-[11px]">
                {days[e.day]} · {formatHour(e.startHour)}
              </div>
            </div>
          </button>
        ))}
      </Card>
    </div>
  )
}

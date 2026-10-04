import type { CalendarEvent } from "../../types/calendar"
import { formatHour } from "../../utils/calendar"
import { Card } from "../ui"

interface CalendarWeekGridProps {
  events: CalendarEvent[]
  days: string[]
  hours: number[]
  projectColors: Record<string, string>
  selectedId: string
  onSelect: (id: string) => void
}

// Overlapping meetings occupy lanes so every meeting remains clickable.
function positionEvents(events: CalendarEvent[]) {
  const ordered = [...events].sort(
    (a, b) => a.startHour - b.startHour || a.id.localeCompare(b.id),
  )
  const result: {
    event: CalendarEvent
    lane: number
    lanes: number
  }[] = []
  let group: typeof result = []
  let ends: number[] = []
  function flush() {
    group.forEach((item) => result.push({ ...item, lanes: ends.length }))
    group = []
    ends = []
  }
  for (const event of ordered) {
    if (ends.length && ends.every((end) => end <= event.startHour)) flush()
    let lane = ends.findIndex((end) => end <= event.startHour)
    if (lane < 0) lane = ends.length
    ends[lane] = event.startHour + event.durationHours
    group.push({ event, lane, lanes: 1 })
  }
  flush()
  return result
}

export default function CalendarWeekGrid({
  events,
  days,
  hours,
  projectColors,
  selectedId,
  onSelect,
}: CalendarWeekGridProps) {
  const columns = `52px repeat(${days.length}, minmax(0, 1fr))`
  return (
    <Card className="overflow-auto flex flex-col lg:min-h-0 order-1 lg:order-2">
      <div
        className="grid border-b border-line text-[12px] font-medium shrink-0 min-w-[440px]"
        style={{ gridTemplateColumns: columns }}
      >
        <div />
        {days.map((day) => (
          <div key={day} className="px-3 py-2 text-mute border-l border-line">
            {day}
          </div>
        ))}
      </div>
      <div
        className="relative grid lg:flex-1 shrink-0 min-w-[440px]"
        style={{
          gridTemplateColumns: columns,
          gridTemplateRows: `repeat(${hours.length}, minmax(44px, 1fr))`,
          minHeight: hours.length * 44,
        }}
      >
        {hours.map((hour, row) => (
          <div key={hour} className="contents">
            <div
              className="text-[10.5px] font-mono text-mute pr-2 text-right -translate-y-1.5"
              style={{ gridRow: row + 1, gridColumn: 1 }}
            >
              {formatHour(hour)}
            </div>
            {days.map((_, column) => (
              <div
                key={column}
                className="border-l border-t border-line"
                style={{ gridRow: row + 1, gridColumn: column + 2 }}
              />
            ))}
          </div>
        ))}
        {days.map((day, column) => (
          <div
            key={day}
            className="relative pointer-events-none"
            style={{
              gridColumn: column + 2,
              gridRow: `1 / span ${hours.length}`,
            }}
          >
            {positionEvents(events.filter((event) => event.day === column)).map(
              ({ event, lane, lanes }) => {
                const proposed = event.kind === "proposed"
                return (
                  <button
                    key={event.id}
                    onClick={() => onSelect(event.id)}
                    aria-label={`${event.title}, ${formatHour(event.startHour)}${
                      proposed ? ", suggested" : ""
                    }`}
                    title={`${event.title} · ${formatHour(event.startHour)} – ${formatHour(event.startHour + event.durationHours)}`}
                    className={`absolute pointer-events-auto rounded-lg px-2 py-1 text-left text-[11.5px] leading-tight overflow-hidden ${
                      selectedId === event.id ? "ring-2 ring-ink/70" : ""
                    } ${
                      proposed
                        ? "border border-dashed bg-amber-soft text-amber-ink"
                        : "text-white"
                    }`}
                    style={{
                      top: `calc(${((event.startHour - hours[0]) / hours.length) * 100}% + 2px)`,
                      height: `calc(${(event.durationHours / hours.length) * 100}% - 4px)`,
                      minHeight: 22,
                      left: `calc(${(lane / lanes) * 100}% + 2px)`,
                      width: `calc(${100 / lanes}% - 4px)`,
                      background: proposed
                        ? undefined
                        : projectColors[event.project],
                      borderColor: proposed ? "#b9882f" : undefined,
                    }}
                  >
                    <b className="block truncate">
                      {proposed && "✦ "}
                      {event.title}
                    </b>
                    <span className="opacity-80 font-mono">
                      {formatHour(event.startHour)}
                    </span>
                  </button>
                )
              },
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

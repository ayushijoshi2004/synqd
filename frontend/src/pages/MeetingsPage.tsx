import { useState } from "react"
import { Search, Plus, SlidersHorizontal } from "lucide-react"
import { createMeeting, getProjectGroups } from "../services/meetings"
import { useMeetings } from "../hooks/useMeetings"
import MeetingFormModal from "../components/meetings/MeetingFormModal"
import MeetingCard from "../components/meetings/MeetingCard"
import MeetingSection from "../components/meetings/MeetingSection"
import { Pill, btnPrimary } from "../components/ui"

export default function MeetingsPage({
  onOpenMeeting,
}: {
  onOpenMeeting: (id: string) => void
}) {
  const { meetings } = useMeetings()
  const [creating, setCreating] = useState(false)
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState("All")
  const [view, setView] = useState<"meetings" | "projects">("meetings")
  const projectGroups = getProjectGroups()
  const projects = ["All", ...projectGroups.map((project) => project.name)]
  const list = meetings.filter(
    (m) =>
      (filter === "All" || m.project === filter) &&
      (
        m.title +
        m.preview +
        m.participants.map((person) => person.name).join(" ")
      )
        .toLowerCase()
        .includes(query.toLowerCase()),
  )

  return (
    <div className="p-6 lg:px-10 lg:py-8 w-full">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-2">
        <div>
          <h1 className="text-[30px] font-semibold tracking-tight">Meetings</h1>
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex bg-soft rounded-lg p-0.5 mr-2">
            {(["meetings", "projects"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`h-7 px-3 rounded-md text-[12.5px] font-medium capitalize transition-colors ${
                  view === v
                    ? "bg-white shadow-sm text-ink"
                    : "text-mute hover:text-ink"
                }`}
              >
                {v} view
              </button>
            ))}
          </div>
          <button className={btnPrimary} onClick={() => setCreating(true)}>
            <Plus size={14} /> New Meeting
          </button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 my-6">
        <label className="flex items-center gap-2 bg-card border border-line rounded-lg px-3 h-9 w-full sm:w-80 text-mute focus-within:border-accent">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search meetings, decisions, people"
            className="flex-1 outline-none text-[13px] text-ink placeholder:text-mute bg-transparent"
          />
        </label>
        <div className="flex items-center gap-1.5">
          <SlidersHorizontal size={14} className="text-mute mr-1" />
          {projects.map((p) => (
            <button
              key={p || "No project"}
              onClick={() => setFilter(p)}
              className={`h-8 px-3 rounded-full text-[12px] font-medium border transition-colors ${
                filter === p
                  ? "bg-ink text-white border-ink"
                  : "bg-card border-line text-mute hover:text-ink"
              }`}
            >
              {p || "No project"}
            </button>
          ))}
        </div>
      </div>
      {view === "meetings" ? (
        <>
          <MeetingSection
            title="Recent Meetings"
            subtitle=""
            meetings={list.filter(
              (meeting) =>
                meeting.status === "ended" || meeting.status === "cancelled",
            )}
            onOpenMeeting={onOpenMeeting}
          />
          <MeetingSection
            title="Upcoming Meetings"
            subtitle=""
            meetings={list.filter(
              (meeting) =>
                meeting.status === "scheduled" ||
                meeting.status === "in_progress",
            )}
            onOpenMeeting={onOpenMeeting}
          />
        </>
      ) : (
        projectGroups.map((project) => {
          const p = project.name
          const items = list.filter((m) => m.project === p)
          if (!items.length) return null
          return (
            <div key={p} className="mb-10">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
                <h2 className="font-semibold text-[17px] tracking-tight">
                  {p || "No project"}
                </h2>
                <span className="text-[12px] text-mute">
                  {items.length} meetings
                </span>
                <Pill tone="Proposed">
                  {project.openActionItems} open action items
                </Pill>
                <span className="text-[12px] rounded-full bg-soft px-2.5 py-0.5 font-mono text-mute">
                  {project.memory}
                </span>
              </div>
              <div className="grid gap-4 grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {items.map((m) => (
                  <MeetingCard
                    key={m.id}
                    meeting={m}
                    onOpen={() => onOpenMeeting(m.id)}
                  />
                ))}
              </div>
            </div>
          )
        })
      )}
      {!list.length && (
        <p className="text-mute text-sm">No meetings match your search.</p>
      )}
      {creating && (
        <MeetingFormModal
          title="New Meeting"
          submitLabel="Create Meeting"
          onClose={() => setCreating(false)}
          onSubmit={async (fields) => {
            await createMeeting(fields)
            setFilter("All")
            setQuery("")
          }}
        />
      )}
    </div>
  )
}

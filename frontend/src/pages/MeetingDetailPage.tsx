import { useEffect, useState } from "react"
import { ArrowLeft, Clock, Users } from "lucide-react"
import { useMeetings } from "../hooks/useMeetings"
import { getMeeting, processMeeting, refreshMeeting } from "../services/meetings"
import {
  aiStatusLabels,
  durationMinutes,
  formatDate,
  formatTimeRange,
  meetingStatusLabels,
} from "../utils/meetings"
import type { MeetingDetail } from "../types/meeting"
import type { MeetingDetailTab } from "../types/navigation"
import { AvatarStack, Pill, btnPrimary } from "../components/ui"
import MeetingContextPanel from "../components/meeting-detail/MeetingContextPanel"
import ProjectOverviewPanel from "../components/meeting-detail/ProjectOverviewPanel"
import MeetingContent from "../components/meeting-detail/MeetingContent"
import TranscriptionControls from "../components/meeting-detail/TranscriptionControls"
import ActionItemsPanel from "../components/meeting-detail/ActionItemsPanel"

interface MeetingDetailPageProps {
  meetingId: string
  onBack: () => void
}

export default function MeetingDetailPage({
  meetingId,
  onBack,
}: MeetingDetailPageProps) {
  const { meetings } = useMeetings()
  const [loadedMeeting, setLoadedMeeting] = useState<MeetingDetail | null>(null)
  const meeting = meetings.find((item) => item.id === meetingId) ?? loadedMeeting
  const [loadState, setLoadState] = useState(meeting ? "ready" : "loading")
  useEffect(() => {
    let cancelled = false
    if (!meeting) setLoadState("loading")
    setLoadedMeeting(null)
    void getMeeting(meetingId).then((saved) => {
      if (!cancelled) {
        setLoadedMeeting(saved)
        setLoadState(saved ? "ready" : "missing")
      }
    }).catch(() => {
      if (!cancelled) setLoadState("error")
    })
    return () => { cancelled = true }
  }, [meetingId])
  const [processing, setProcessing] = useState(false)
  const [processingError, setProcessingError] = useState("")
  useEffect(() => {
    if (meeting?.aiStatus !== "processing") return
    const timer = window.setInterval(() => { void refreshMeeting(meetingId).catch(() => {}) }, 2000)
    return () => window.clearInterval(timer)
  }, [meetingId, meeting?.aiStatus])

  async function process() {
    if (processing) return
    setProcessing(true)
    setProcessingError("")
    try {
      await processMeeting(meetingId)
    } catch (error) {
      setProcessingError(error instanceof Error ? error.message : "AI processing unavailable.")
    } finally {
      setProcessing(false)
    }
  }
  const [tab, setTab] = useState<MeetingDetailTab>("summary")
  const [highlightedTimestamp, setHighlightedTimestamp] =
    useState<string | null>(null)

  function jump(timestamp: string) {
    setHighlightedTimestamp(timestamp)
    setTab("transcript")
  }

  if (loadState !== "ready" || !meeting) {
    return (
      <div className="p-5 lg:px-8">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[13px] text-mute hover:text-ink"
          aria-label="All meetings"
        >
          <ArrowLeft size={15} />
        </button>
        <p className="text-mute text-sm mt-4" role="status">
          {loadState === "loading" ? "Loading meeting and Ask Synqd..." :
            loadState === "error" ? "Unable to load this meeting. Please reload the page." : "Meeting not found."}
        </p>
      </div>
    )
  }

  const projectTasks = meetings
    .filter((item) =>
      meeting.project
        ? item.project === meeting.project
        : item.id === meeting.id,
    )
    .flatMap((item) => item.actionItems)
  return (
    <div className="p-5 lg:px-8 xl:h-[calc(100vh-3.5rem)] xl:flex xl:flex-col xl:overflow-hidden">
      <header className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 shrink-0">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[13px] text-mute hover:text-ink"
          aria-label="All meetings"
        >
          <ArrowLeft size={15} />
        </button>
        <h1 className="text-[22px] font-semibold tracking-tight">
          {meeting.title}
        </h1>
        <Pill tone={meeting.status}>{meetingStatusLabels[meeting.status]}</Pill>
        <Pill tone={meeting.aiStatus}>{aiStatusLabels[meeting.aiStatus]}</Pill>
        <button
          className={btnPrimary}
          disabled={processing || meeting.aiStatus === "processing" || !meeting.transcript.some((line) => line.text.trim())}
          onClick={() => void process()}
        >
          {processing || meeting.aiStatus === "processing" ? "Processing…" :
            meeting.aiStatus === "failed" || processingError ? "Retry processing" :
            meeting.aiStatus === "processed" ? "Process again" : "Process Meeting"}
        </button>
        <span className="flex items-center gap-1.5 text-[12.5px] text-mute font-mono">
          <Clock size={13} /> {formatDate(meeting.date)} ·{" "}
          {formatTimeRange(meeting)}
          {` · ${durationMinutes(meeting)} min`}
        </span>
        <span className="flex items-center gap-2 text-[12.5px] text-mute">
          <Users size={13} />{" "}
          <AvatarStack participants={meeting.participants} size={22} />{" "}
          <span className="hidden md:inline">
            {meeting.participants.map((p) => p.name.split(" ")[0]).join(", ")}
          </span>
        </span>
      </header>
      <TranscriptionControls key={meeting.id} meeting={meeting} />
      {(processingError || meeting.aiStatus === "failed") && (
        <p role="alert" className="mb-3 text-[13px] text-red-700">
          {processingError || "AI processing unavailable. Your meeting and transcript are still saved."}
        </p>
      )}
      {!meeting.transcript.some((line) => line.text.trim()) && (
        <p className="mb-3 text-[13px] text-mute">Save a transcript before processing this meeting.</p>
      )}
      <div className="grid gap-4 xl:grid-cols-[250px_minmax(0,1fr)_340px] xl:flex-1 xl:min-h-0">
        <MeetingContextPanel meeting={meeting} onJump={jump} />
        <div className="flex flex-col gap-4 order-3 xl:order-2 min-w-0 xl:min-h-0">
          <ProjectOverviewPanel
            project={meeting.projectOverview}
            actionItems={projectTasks}
          />
          <MeetingContent
            meeting={meeting}
            tab={tab}
            onTabChange={setTab}
            highlightedTimestamp={highlightedTimestamp}
            onTranscriptSelect={setHighlightedTimestamp}
          />
        </div>
        <div className="order-1 xl:order-3 xl:min-h-0 flex flex-col">
          <ActionItemsPanel
            meetingId={meeting.id}
            actionItems={meeting.actionItems}
          />
        </div>
      </div>
    </div>
  )
}

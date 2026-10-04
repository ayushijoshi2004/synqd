import { useState } from "react"
import AppHeader from "./components/AppHeader"
import type { AppScreen } from "./types/navigation"
import MeetingsPage from "./pages/MeetingsPage"
import MeetingDetailPage from "./pages/MeetingDetailPage"
import CalendarPage from "./pages/CalendarPage"

export default function App() {
  const [screen, setScreen] = useState<AppScreen>("meetings")
  const [meetingId, setMeetingId] = useState("m1")
  return (
    <div className="min-h-screen">
      <AppHeader
        activeTab={screen === "calendar" ? "calendar" : "meetings"}
        onNavigate={setScreen}
      />
      <main>
        {screen === "meetings" && (
          <MeetingsPage
            onOpenMeeting={(id) => {
              setMeetingId(id)
              setScreen("meeting-detail")
              window.scrollTo(0, 0)
            }}
          />
        )}
        {screen === "meeting-detail" && (
          <MeetingDetailPage
            key={meetingId}
            meetingId={meetingId}
            onBack={() => setScreen("meetings")}
          />
        )}
        {screen === "calendar" && (
          <CalendarPage
            onOpenMeeting={(id) => {
              setMeetingId(id)
              setScreen("meeting-detail")
              window.scrollTo(0, 0)
            }}
          />
        )}
      </main>
    </div>
  )
}

import { Sparkles } from "lucide-react"
import type { NavigationTab } from "../types/navigation"

interface AppHeaderProps {
  activeTab: NavigationTab
  onNavigate: (tab: NavigationTab) => void
}

export default function AppHeader({ activeTab, onNavigate }: AppHeaderProps) {
  return (
    <header className="sticky top-0 z-10 flex items-center gap-6 px-6 lg:px-10 h-14 border-b border-line bg-bg/90 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="size-7 rounded-lg bg-accent text-white flex items-center justify-center">
          <Sparkles size={15} />
        </span>
        <span className="font-semibold tracking-tight">Synqd</span>
      </div>
      <nav className="flex gap-1">
        {(["meetings", "calendar"] as const).map((t) => (
          <button
            key={t}
            onClick={() => onNavigate(t)}
            className={`h-8 px-3 rounded-lg text-[13px] capitalize transition-colors ${
              activeTab === t
                ? "bg-soft font-medium"
                : "text-mute hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
    </header>
  )
}

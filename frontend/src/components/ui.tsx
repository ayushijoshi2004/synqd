import type { Participant } from "../types/meeting"
import type { ReactNode } from "react"

export function Avatar({
  participant,
  size = 24,
}: {
  participant: Participant
  size?: number
}) {
  const p = participant
  return (
    <span
      title={p.name}
      className="inline-flex items-center justify-center rounded-full text-white font-semibold ring-2 ring-white shrink-0"
      style={{
        width: size,
        height: size,
        background: p.color,
        fontSize: size * 0.4,
      }}
    >
      {p.name
        .split(" ")
        .map((n) => n[0])
        .join("")}
    </span>
  )
}

export function AvatarStack({
  participants,
  size = 24,
}: {
  participants: Participant[]
  size?: number
}) {
  return (
    <span className="flex -space-x-1.5">
      {participants.map((participant) => (
        <Avatar key={participant.id} participant={participant} size={size} />
      ))}
    </span>
  )
}

const tones: Record<string, string> = {
  processed: "bg-accent-soft text-accent",
  ended: "bg-accent-soft text-accent",
  scheduled: "bg-soft text-mute",
  in_progress: "bg-red-50 text-red-700",
  cancelled: "bg-soft text-mute",
  unprocessed: "bg-soft text-mute",
  processing: "bg-amber-soft text-amber-ink",
  failed: "bg-red-50 text-red-700",
  Live: "bg-red-50 text-red-700",
  Upcoming: "bg-soft text-mute",
  Processing: "bg-amber-soft text-amber-ink",
  Proposed: "bg-amber-soft text-amber-ink",
}
export function Pill({
  children,
  tone,
}: {
  children: ReactNode
  tone?: string
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${tones[tone ?? String(children)] ?? "bg-soft text-mute"}`}
    >
      {children}
    </span>
  )
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={`bg-card border border-line rounded-2xl shadow-[0_1px_2px_rgba(20,25,22,0.04)] ${className}`}
    >
      {children}
    </section>
  )
}

export function CardHead({
  icon,
  title,
  right,
}: {
  icon?: ReactNode
  title: string
  right?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between px-5 pt-4 pb-3">
      <h3 className="flex items-center gap-2 text-[13px] font-semibold tracking-tight">
        {icon && <span className="text-accent">{icon}</span>}
        {title}
      </h3>
      {right}
    </div>
  )
}

export const btn =
  "inline-flex items-center justify-center gap-1.5 rounded-lg text-[13px] font-medium h-8 px-3 transition-colors"
export const btnPrimary = `${btn} bg-accent text-white hover:bg-[#265a4c] disabled:opacity-40 disabled:cursor-not-allowed`
export const btnGhost = `${btn} border border-line bg-white hover:bg-soft text-ink`

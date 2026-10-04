import { Check, Pencil, X } from "lucide-react"
import type { FollowUpMeeting } from "../../types/calendar"
import { formatDate, formatTime } from "../../utils/meetings"
import { Card, Pill, btnPrimary, btnGhost } from "../ui"

interface CalendarApprovalsProps {
  proposals: FollowUpMeeting[]
  pending: boolean
  onApprove: (id: string) => void
  onEdit: (id: string) => void
  onDismiss: (id: string) => void
}

export default function CalendarApprovals({
  proposals,
  pending,
  onApprove,
  onEdit,
  onDismiss,
}: CalendarApprovalsProps) {
  return (
    <div className="flex flex-col gap-3 lg:min-h-0 order-3">
      <Card className="p-3.5 lg:flex-1 lg:min-h-0 lg:overflow-auto">
        <h3 className="text-[13px] font-semibold mb-3 flex items-center gap-2">
          Awaiting approval <Pill tone="Proposed">{proposals.length}</Pill>
        </h3>
        <div className="space-y-2.5">
          {proposals.map((e) => (
            <div
              key={e.id}
              className="rounded-xl border border-dashed border-amber-ink/30 bg-amber-soft/50 p-3"
            >
              <p className="text-[13px] font-medium">{e.title}</p>
              <p className="text-[11.5px] text-mute font-mono mt-0.5">
                {e.date ? formatDate(e.date) : "Date to be chosen"} · {e.startTime ? formatTime(e.startTime) : "Time to be chosen"}
              </p>
              <p className="text-[11px] text-amber-ink mt-1">Suggested</p>
              <div className="flex gap-1.5 mt-2.5">
                <button
                  disabled={pending}
                  onClick={() => onApprove(e.id)}
                  className={`${btnPrimary} h-7 px-2.5 text-[12px]`}
                >
                  <Check size={12} /> Approve
                </button>
                <button
                  disabled={pending}
                  onClick={() => onEdit(e.id)}
                  className={`${btnGhost} h-7 px-2.5 text-[12px]`}
                >
                  <Pencil size={12} /> Edit
                </button>
                <button
                  disabled={pending}
                  onClick={() => onDismiss(e.id)}
                  className={`${btnGhost} h-7 px-2.5 text-[12px]`}
                >
                  <X size={12} /> Dismiss
                </button>
              </div>
            </div>
          ))}
          {!proposals.length && (
            <p className="text-[12.5px] text-mute">Nothing pending.</p>
          )}
        </div>
      </Card>
    </div>
  )
}

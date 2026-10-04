import { useState } from "react"
import { ListChecks, Ticket } from "lucide-react"
import type { ActionItem, ActionItemStatus } from "../../types/meeting"
import {
  createActionItemTickets,
  updateActionItemStatus,
} from "../../services/actionItems"
import { safeHttpUrl } from "../../utils/meetings"
import { Avatar, Card, CardHead, btnPrimary } from "../ui"

export default function ActionItemsPanel({
  meetingId,
  actionItems,
}: {
  meetingId: string
  actionItems: ActionItem[]
}) {
  const [picked, setPicked] = useState<string[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const open = actionItems.filter((item) => item.status !== "done")
  async function run(update: () => Promise<void>) {
    if (pending) return
    setPending(true)
    setError(null)
    try {
      await update()
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to update tasks.",
      )
    } finally {
      setPending(false)
    }
  }
  async function make(ids: string[]) {
    await run(async () => {
      await createActionItemTickets(meetingId, ids)
      setPicked([])
    })
  }
  return (
    <Card className="border-accent/40 shadow-[0_6px_24px_rgba(47,111,94,0.10)] xl:flex-1 xl:min-h-0 flex flex-col">
      <CardHead
        icon={<ListChecks size={15} />}
        title="Action Items"
        right={
          <span className="text-[11px] text-mute">{open.length} open</span>
        }
      />
      <div className="px-3 pb-3 space-y-1 xl:flex-1 xl:overflow-auto">
        {!actionItems.length && (
          <p className="p-3 text-[13px] text-mute">No action items yet.</p>
        )}
        {actionItems.map((task) => {
          const on = picked.includes(task.id)
          return (
            <div
              key={task.id}
              className={`rounded-xl p-3 border transition-colors ${
                on
                  ? "border-accent/40 bg-accent-soft/50"
                  : "border-transparent hover:bg-soft"
              }`}
            >
              <label className="flex items-start gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  aria-label={`Select ${task.text} for Jira`}
                  disabled={!!task.jiraIssueKey || pending}
                  checked={on}
                  onChange={() =>
                    setPicked((current) =>
                      on
                        ? current.filter((id) => id !== task.id)
                        : [...current, task.id],
                    )
                  }
                  className="mt-0.5 size-4 accent-[#2f6f5e]"
                />
                <span
                  className={`text-[13px] font-medium leading-snug ${
                    task.status === "done" ? "text-mute line-through" : ""
                  }`}
                >
                  {task.text}
                </span>
              </label>
              <div className="flex flex-wrap items-center gap-2 mt-2 pl-6.5 text-[11.5px] text-mute">
                {task.assignee ? <Avatar participant={task.assignee} size={20} /> : <span>Unassigned</span>}
                <span className="font-mono">{task.due}</span>
                <select
                  aria-label={`Status for ${task.text}`}
                  value={task.status}
                  disabled={pending}
                  onChange={(event) =>
                    void run(() =>
                      updateActionItemStatus(
                        meetingId,
                        task.id,
                        event.target.value as ActionItemStatus,
                      ),
                    )
                  }
                  className="ml-auto rounded-md border border-line bg-white px-1 py-0.5 text-ink"
                >
                  <option value="todo">To do</option>
                  <option value="in_progress">In progress</option>
                  <option value="done">Done</option>
                </select>
                {task.jiraIssueKey ? (
                  safeHttpUrl(task.jiraIssueUrl) ? (
                    <a
                      href={safeHttpUrl(task.jiraIssueUrl)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-mono text-accent flex items-center gap-1 hover:underline"
                    >
                      <Ticket size={12} />
                      {task.jiraIssueKey}
                    </a>
                  ) : (
                    <span className="font-mono text-accent flex items-center gap-1">
                      <Ticket size={12} />
                      {task.jiraIssueKey}
                    </span>
                  )
                ) : (
                  <button
                    disabled={pending}
                    onClick={() => void make([task.id])}
                    className="text-accent font-medium hover:underline"
                  >
                    Create Jira Ticket
                  </button>
                )}
              </div>
            </div>
          )
        })}
        {error && (
          <p role="alert" className="text-[12.5px] text-mute">
            {error}
          </p>
        )}
        <button
          disabled={!picked.length || pending}
          onClick={() => void make(picked)}
          className={`${btnPrimary} w-full mt-2`}
        >
          <Ticket size={14} />
          {picked.length
            ? `Create ${picked.length} Jira ticket${
                picked.length > 1 ? "s" : ""
              }`
            : "Select tasks to convert"}
        </button>
      </div>
    </Card>
  )
}

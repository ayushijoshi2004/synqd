import { ArrowRight, Layers } from "lucide-react"
import type { ActionItem, ProjectOverview } from "../../types/meeting"
import { safeHttpUrl } from "../../utils/meetings"
import { Card, CardHead } from "../ui"

interface ProjectOverviewPanelProps {
  project: ProjectOverview
  actionItems: ActionItem[]
}

export default function ProjectOverviewPanel({
  project,
  actionItems,
}: ProjectOverviewPanelProps) {
  const doneCount = actionItems.filter((item) => item.status === "done").length
  const totalTasks = actionItems.length
  const ticketCount = actionItems.filter((item) => item.jiraIssueKey).length
  return (
    <Card className="shrink-0">
      <CardHead
        icon={<Layers size={15} />}
        title="Project Overview"
        right={
          safeHttpUrl(project.jiraProjectUrl) ? (
            <a
              href={safeHttpUrl(project.jiraProjectUrl)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[12.5px] text-mute hover:text-ink flex items-center gap-1"
            >
              Open Jira <ArrowRight size={13} />
            </a>
          ) : (
            <button
              disabled
              title="No Jira project URL configured"
              className="text-[12.5px] text-mute opacity-50 disabled:cursor-not-allowed flex items-center gap-1"
            >
              Open Jira <ArrowRight size={13} />
            </button>
          )
        }
      />
      <div className="px-5 pb-4">
        <p className="text-[14px] font-semibold">{project.name}</p>
        {project.description && (
          <p className="text-[12.5px] text-mute">
            {`${project.description} Launch `}
            <span className="line-through">{project.previousLaunchDate}</span>
            {" → "}
            <b className="text-ink">{project.launchDate}</b>.
          </p>
        )}
        <div className="mt-3 text-[12.5px] font-medium">
          {doneCount}
          {` of ${totalTasks} tasks completed`}
        </div>
        <div className="mt-1.5 h-1.5 rounded-full bg-soft overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all"
            style={{
              width: `${totalTasks ? (doneCount / totalTasks) * 100 : 0}%`,
            }}
          />
        </div>
        <div className="grid grid-cols-2 gap-6 mt-4 pt-4 border-t border-line text-[12.5px]">
          <div>
            <div className="text-[10.5px] uppercase tracking-wider text-mute font-semibold mb-1.5">
              Key resources
            </div>
            <ul className="space-y-1 text-[#3c403e]">
              {project.resources.map((r) => (
                <li key={r}>{r}</li>
              ))}
              {project.additionalResourceCount > 0 && (
                <li className="font-medium">{`+${project.additionalResourceCount} more`}</li>
              )}
            </ul>
          </div>
          <div>
            <div className="text-[10.5px] uppercase tracking-wider text-mute font-semibold mb-1.5">
              Related
            </div>
            <ul className="space-y-1 text-[#3c403e]">
              <li>{ticketCount} Jira tickets</li>
              <li>{`${project.previousMeetingCount} previous meetings`}</li>
              {project.relatedResources.map((resource) => (
                <li key={resource}>{resource}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </Card>
  )
}

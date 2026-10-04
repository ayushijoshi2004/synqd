import { participants } from "./participants"
import type { Meeting, MeetingDetail, MeetingProject } from "../types/meeting"

export const meetings: Meeting[] = [
  {
    id: "m1",
    title: "Atlas Launch Readiness",
    date: "2026-09-29",
    startTime: "10:00",
    endTime: "10:48",
    agenda:
      "QA status\nPayment edge cases\nLaunch date\nDesign scope\nNext meeting",
    project: "Atlas Launch",
    team: "Product",
    status: "ended",
    aiStatus: "processed",
    preview:
      "Launch moves to Oct 22 after QA flagged payment edge cases. 5 action items, 2 decisions.",
    participants: [
      participants.maya,
      participants.alex,
      participants.priya,
      participants.sam,
    ],
  },
  {
    id: "m2",
    title: "Onboarding Flow Critique",
    date: "2026-09-26",
    startTime: "14:00",
    endTime: "14:40",
    agenda: "Review onboarding steps",
    project: "Atlas Launch",
    team: "Design",
    status: "ended",
    aiStatus: "processed",
    preview:
      "Team agreed to cut the onboarding from 6 steps to 4. Drop-off data drove the call.",
    participants: [participants.priya, participants.jo, participants.maya],
  },
  {
    id: "m3",
    title: "Weekly Growth Sync",
    date: "2026-09-25",
    startTime: "09:30",
    endTime: "10:05",
    agenda: "Referral conversion",
    project: "Growth Loop",
    team: "Marketing",
    status: "ended",
    aiStatus: "processing",
    preview:
      "Transcript is being analyzed. Early signal: referral conversion up 12% week over week.",
    participants: [participants.sam, participants.jo],
  },
  {
    id: "m4",
    title: "Design Review",
    date: "2026-10-06",
    startTime: "14:00",
    endTime: "14:45",
    agenda: "Final checkout states\nEmpty states\nMotion specs",
    project: "Atlas Launch",
    team: "Design",
    status: "scheduled",
    aiStatus: "unprocessed",
    preview:
      "Suggested agenda from last meeting: final checkout states, empty states, motion specs.",
    participants: [participants.maya, participants.alex, participants.priya],
  },
  {
    id: "m5",
    title: "Q4 Roadmap Planning",
    date: "2026-10-08",
    startTime: "11:00",
    endTime: "12:00",
    agenda: "Review Q4 themes and unresolved decisions",
    project: "Roadmap",
    team: "Leadership",
    status: "scheduled",
    aiStatus: "unprocessed",
    preview:
      "AI brief: 3 unresolved decisions carried over from the September planning session.",
    participants: [
      participants.maya,
      participants.sam,
      participants.jo,
      participants.alex,
    ],
  },
  {
    id: "m6",
    title: "Customer Interview: Northwind",
    date: "2026-10-09",
    startTime: "15:30",
    endTime: "16:15",
    agenda: "Discuss bulk export needs",
    project: "Growth Loop",
    team: "Research",
    status: "scheduled",
    aiStatus: "unprocessed",
    preview:
      "Prep notes pulled from 4 earlier interviews mentioning bulk export.",
    participants: [participants.jo, participants.priya],
  },
]

export const meetingProjects: MeetingProject[] = [
  {
    name: "Atlas Launch",
    memory: "Launch date: Oct 15 → Oct 22",
    openActionItems: 5,
  },
  {
    name: "Growth Loop",
    memory: "Referral target: 8% → 10%",
    openActionItems: 3,
  },
  {
    name: "Roadmap",
    memory: "Q4 themes: 4 → 3",
    openActionItems: 2,
  },
]

// Rich local results belong to Atlas Launch Readiness only.
export const sharedMeetingDetail: Omit<MeetingDetail, keyof Meeting> = {
  agendaEntries: [
    {
      title: "QA status",
      timestamp: "00:42",
      completed: true,
    },
    {
      title: "Payment edge cases",
      timestamp: "03:15",
      completed: true,
    },
    {
      title: "Launch date",
      timestamp: "18:54",
      completed: true,
    },
    {
      title: "Design scope",
      timestamp: "12:30",
      completed: true,
    },
    {
      title: "Next meeting",
      timestamp: "31:05",
      completed: false,
    },
  ],
  summary: {
    beforeHighlight: "The team is moving the Atlas launch to ",
    highlight: "October 22",
    afterHighlight:
      " to fix two payment bugs, add a status page, and lock design scope by Friday.",
    points: [
      "QA found 2 payment edge cases: declined retries and JPY rounding.",
      "Support needs a customer status page before go-live.",
      "Design commits to checkout error states by Oct 3.",
    ],
  },
  transcript: [
    {
      timestamp: "00:42",
      speaker: participants.maya,
      text: "Let's start with where QA landed. Anything blocking us for the 15th?",
    },
    {
      timestamp: "03:15",
      speaker: participants.alex,
      text: "Two payment edge cases: declined cards on retry, and currency rounding for JPY.",
    },
    {
      timestamp: "06:08",
      speaker: participants.sam,
      text: "Support is also asking for a status page before launch. That's a real risk if we slip.",
    },
    {
      timestamp: "12:30",
      speaker: participants.priya,
      text: "Design can finish the checkout error states by Friday if we lock scope today.",
    },
    {
      timestamp: "18:54",
      speaker: participants.maya,
      text: "Then I propose we move launch to October 22 and use the week for hardening.",
    },
    {
      timestamp: "19:40",
      speaker: participants.alex,
      text: "Agreed. I'll file tickets for both payment bugs today.",
    },
    {
      timestamp: "31:05",
      speaker: participants.maya,
      text: "Let's hold a design review next Tuesday at 2 PM with Alex and Priya.",
    },
  ],
  decisions: [
    {
      id: "d1",
      text: "Move Atlas launch from October 15 to October 22.",
      note: "Driven by two open payment bugs and a missing status page.",
      participant: participants.maya,
      timestamp: "18:54",
    },
    {
      id: "d2",
      text: "Lock checkout scope today; no new states after Friday.",
      note: "Design commits to Friday delivery in exchange.",
      participant: participants.priya,
      timestamp: "12:30",
    },
  ],
  actionItems: [
    {
      id: "t1",
      text: "Fix declined-card retry bug",
      due: "Oct 1",
      status: "todo",
      assignee: participants.alex,
    },
    {
      id: "t2",
      text: "Patch JPY currency rounding",
      due: "Oct 2",
      status: "in_progress",
      assignee: participants.alex,
    },
    {
      id: "t3",
      text: "Finish checkout error states",
      due: "Oct 3",
      status: "todo",
      assignee: participants.priya,
    },
    {
      id: "t4",
      text: "Publish customer status page",
      due: "Oct 10",
      status: "todo",
      assignee: participants.sam,
    },
    {
      id: "t5",
      text: "Update launch comms timeline",
      due: "Oct 6",
      status: "done",
      assignee: participants.maya,
    },
  ],
  projectOverview: {
    name: "Atlas Launch",
    description: "Ship the new checkout and onboarding experience.",
    previousLaunchDate: "Oct 15",
    launchDate: "Oct 22",
    resources: [
      "Launch Brief.pdf",
      "Payment QA Report",
      "Checkout Wireframes.fig",
      "Launch Comms Plan",
    ],
    additionalResourceCount: 2,
    previousMeetingCount: 6,
    relatedResources: ["Project timeline", "Brand assets"],
  },
  assistant: {
    scopeLabel: "Searching 18 meetings across 3 projects",
    suggestions: [
      "What did we decide about the launch date?",
      "What are my action items?",
      "What changed from our last meeting?",
    ],
  },
}

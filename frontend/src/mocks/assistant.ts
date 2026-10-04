import type { AssistantAnswer } from "../types/meeting"

export const answers: Record<string, AssistantAnswer> = {
  "What did we decide about the launch date?": {
    text: "Launch moves from October 15 to October 22. Maya proposed it at 18:54 after Alex reported two open payment bugs; the extra week is reserved for hardening and the status page.",
    sources: [
      "Atlas Launch Readiness · 18:54",
      "Onboarding Flow Critique · Sep 26",
    ],
  },
  "What are my action items?": {
    text: "You have 2 open items: finish the checkout error states (due Oct 3) and review the onboarding copy from last Friday's critique.",
    sources: [
      "Atlas Launch Readiness · 12:30",
      "Onboarding Flow Critique · 24:10",
    ],
  },
  "What changed from our last meeting?": {
    text: "Three changes since Sep 26: launch date slipped by 7 days, onboarding was trimmed to 4 steps (unchanged), and a customer status page was added to scope.",
    sources: ["Project memory · Atlas Launch"],
  },
}

export function getFallbackAnswer(meetingTitle: string): AssistantAnswer {
  return {
    text: `Searching across Atlas Launch, Growth Loop and 14 earlier meetings… The closest match is from “${meetingTitle}”: the team discussed this alongside the Oct 22 launch plan. Want me to open the transcript at that point?`,
    sources: [meetingTitle + " · 06:08"],
  }
}

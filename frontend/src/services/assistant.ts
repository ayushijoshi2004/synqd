import { config } from "../config/env"
import type { AssistantAnswer, AssistantMessage } from "../types/meeting"

export async function askMeetingQuestion(
  meetingId: string,
  question: string,
  history: AssistantMessage[] = [],
): Promise<AssistantAnswer> {
  if (!question.trim()) throw new Error("Please enter a question.")
  if (question.length > 2000) throw new Error("Please keep your question under 2,000 characters.")
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 60_000)
  try {
    const response = await fetch(
      `${config.apiBaseUrl}/meetings/${encodeURIComponent(meetingId)}/ask`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          question: question.trim(),
          history: history.filter((turn) => turn.answer).slice(-6).map((turn) => ({
            question: turn.question, answer: turn.answer!.text,
          })),
        }),
      },
    )
    if (!response.ok) {
      if (response.status === 404) throw new Error("This meeting could not be found. Please reload the page.")
      if (response.status === 413) throw new Error("This meeting has too much content for Ask Synqd to process safely.")
      throw new Error("Ask Synqd is temporarily unavailable. Please try again shortly.")
    }
    const data: unknown = await response.json()
    if (!data || typeof data !== "object" || !("answer" in data) ||
        typeof data.answer !== "string" || !data.answer.trim()) {
      throw new Error("Ask Synqd returned an incomplete answer. Please try again.")
    }
    return { text: data.answer, sources: [] }
  } catch (error) {
    // Only our own fixed messages may reach the UI, never a provider response.
    if (error instanceof Error && [
      "This meeting could not be found. Please reload the page.",
      "This meeting has too much content for Ask Synqd to process safely.",
      "Ask Synqd returned an incomplete answer. Please try again.",
    ].includes(error.message)) throw error
    throw new Error("Ask Synqd is temporarily unavailable. Please try again shortly.")
  } finally {
    clearTimeout(timeout)
  }
}

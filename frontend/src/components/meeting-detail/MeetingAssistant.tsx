import { useEffect, useRef, useState } from "react"
import { Send } from "lucide-react"
import type { AssistantMessage } from "../../types/meeting"
import { askMeetingQuestion } from "../../services/assistant"
import { btnPrimary } from "../ui"

interface MeetingAssistantProps {
  meetingId: string
  active: boolean
}

const suggestions = ["What were the main decisions?", "What are the unresolved issues?", "Summarize this meeting in 3 bullets."]

export default function MeetingAssistant({ meetingId, active }: MeetingAssistantProps) {
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [input, setInput] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef(false)
  const conversation = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const area = conversation.current
    if (area) area.scrollTop = area.scrollHeight
  }, [messages, pending, active])

  async function ask(question: string) {
    question = question.trim()
    if (!question || inFlight.current) return
    inFlight.current = true
    const index = messages.length
    setMessages((current) => [...current, { question }])
    setInput("")
    setPending(true)
    setError(null)
    try {
      const answer = await askMeetingQuestion(meetingId, question, messages)
      setMessages((current) => current.map((turn, i) => i === index ? { ...turn, answer } : turn))
    } catch (error) {
      setError(error instanceof Error ? error.message : "Unable to answer this question. Please try again.")
      setInput(question)
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }

  if (!active) return null
  return (
    <div className="p-4 xl:flex-1 xl:min-h-0 flex flex-col">
      <h2 className="text-[15px] font-semibold">Ask Synqd</h2>
      <p className="text-[11.5px] text-mute mt-1 mb-3">Answers use only this meeting’s saved transcript and intelligence.</p>
      <div ref={conversation} role="log" aria-label="Ask Synqd conversation" aria-live="polite"
        className="min-h-32 xl:flex-1 max-h-72 xl:max-h-none overflow-auto space-y-4 rounded-xl bg-bg p-4">
        {!messages.length && <p className="text-[13px] text-mute">Ask about decisions, responsibilities, or deadlines. If the meeting has no supporting information yet, Synqd will say so.</p>}
        {messages.map((turn, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-ink text-white text-[13px] px-3.5 py-2 w-fit whitespace-pre-wrap break-words">
              <span className="sr-only">You: </span>{turn.question}
            </div>
            {turn.answer && <div className="max-w-[90%] rounded-2xl rounded-bl-md bg-white border border-line text-[13px] px-3.5 py-3 leading-relaxed whitespace-pre-wrap break-words">
              <span className="block text-[11px] font-semibold text-accent mb-1">Synqd</span>{turn.answer.text}
            </div>}
          </div>
        ))}
        {pending && <p role="status" className="text-[13px] text-mute animate-pulse">Synqd is thinking...</p>}
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        {suggestions.map((suggestion) => <button key={suggestion} disabled={pending} onClick={() => void ask(suggestion)}
          className="text-[12px] rounded-full border border-line px-3 py-1.5 hover:border-accent/50 hover:bg-accent-soft/40 transition-colors disabled:opacity-50">
          {suggestion}
        </button>)}
      </div>
      {error && <p role="alert" className="text-[12.5px] text-mute mt-2">{error}</p>}
      <form onSubmit={(event) => { event.preventDefault(); void ask(input) }} className="mt-3 flex gap-2">
        <textarea value={input} onChange={(event) => setInput(event.target.value)} maxLength={2000} rows={2}
          disabled={pending} aria-label="Question about this meeting" placeholder="Ask anything about this meeting..."
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              void ask(input)
            }
          }}
          className="flex-1 min-w-0 rounded-xl border border-line px-3.5 py-2 text-[13px] outline-none focus:border-accent resize-none disabled:opacity-60" />
        <button type="submit" disabled={pending || !input.trim()} className={`${btnPrimary} h-10 px-3 disabled:opacity-50`}>
          <Send size={15} /> Send
        </button>
      </form>
    </div>
  )
}

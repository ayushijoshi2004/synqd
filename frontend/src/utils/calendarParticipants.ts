import type { Participant } from "../types/meeting"

// Names still work as before. Email is optional and never guessed from a name.
export function parseParticipants(input: string, known: Participant[]): Participant[] {
  return input.split(/[,;\n]/).map((value) => value.trim()).filter(Boolean).map((value) => {
    const match = value.match(/^(.+?)\s*<([^<>]+)>$/)
    const name = match ? match[1].trim() : value
    const email = match ? match[2].trim() : value.includes("@") ? value : undefined
    if ((/[<>]/.test(value) && !match) || (email && !/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(email)))
      throw new Error("Use a valid participant email, such as Maya Chen <maya@example.com>.")
    const existing = known.find((person) => person.name.toLowerCase() === name.toLowerCase())
    return {
      ...(existing ?? { id: crypto.randomUUID(), name, color: "#2f6f5e" }),
      ...(email ? { email } : {}),
    }
  })
}

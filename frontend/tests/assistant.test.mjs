import assert from "node:assert/strict"
import test from "node:test"
import { createServer } from "vite"
import React from "react"
import { renderToStaticMarkup } from "react-dom/server"

await test("Ask Synqd API and initial UI", async (t) => {
  const server = await createServer({ configFile: false, optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null }, appType: "custom" })
  t.after(() => server.close())
  const realFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = realFetch })
  const { askMeetingQuestion } = await server.ssrLoadModule("/src/services/assistant.ts")
  let sent
  globalThis.fetch = async (url, init) => {
    sent = { url, init, body: JSON.parse(init.body) }
    return new Response(JSON.stringify({ answer: "Alex Rivera owns the retry bug." }))
  }
  const result = await askMeetingQuestion("meeting/a", " Who owns the retry bug? ", [
    { question: "Unanswered" }, ...Array.from({ length: 8 }, (_, i) => ({ question: `q${i}`, answer: { text: `a${i}`, sources: [] } })),
  ])
  assert.equal(result.text, "Alex Rivera owns the retry bug.")
  assert.ok(sent.url.endsWith("/meetings/meeting%2Fa/ask"))
  assert.equal(sent.init.method, "POST")
  assert.equal(sent.body.question, "Who owns the retry bug?")
  assert.equal(sent.body.history.length, 6)
  assert.deepEqual(sent.body.history[0], { question: "q2", answer: "a2" })
  await assert.rejects(askMeetingQuestion("m1", " "), /enter a question/)
  await assert.rejects(askMeetingQuestion("m1", "q".repeat(2001)), /2,000/)
  for (const status of [400, 404, 413, 503]) {
    globalThis.fetch = async () => new Response(JSON.stringify({ error: { message: "PRIVATE PROVIDER ERROR" } }), { status })
    await assert.rejects(askMeetingQuestion("m1", "q"), (error) => !error.message.includes("PRIVATE") && /meeting|unavailable/.test(error.message))
  }
  globalThis.fetch = async () => { throw new Error("PRIVATE NETWORK ERROR") }
  await assert.rejects(askMeetingQuestion("m1", "q"), /temporarily unavailable/)
  globalThis.fetch = async () => new Response('{"answer":null}')
  await assert.rejects(askMeetingQuestion("m1", "q"), /incomplete answer/)
  const { default: Assistant } = await server.ssrLoadModule("/src/components/meeting-detail/MeetingAssistant.tsx")
  const html = renderToStaticMarkup(React.createElement(Assistant, { meetingId: "m1", active: true }))
  assert.match(html, /Ask Synqd/)
  assert.match(html, /Ask anything about this meeting\.\.\./)
  assert.match(html, /<button[^>]*type="submit"[^>]*disabled/)
  assert.match(html, /role="log"/)
  assert.doesNotMatch(html, /every meeting in your projects/)
})
